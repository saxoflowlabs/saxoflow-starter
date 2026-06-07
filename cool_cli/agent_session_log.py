"""User-facing agent session transparency logs.

The logs in this module are distinct from Python debug logs. They are designed
for SaxoFlow users who want to inspect what the assistant did during a TUI
session: selected intents, agent routing, files touched, command results, and
final responses. They do not expose hidden model chain-of-thought.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Optional

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from saxoflow.runtime_paths import (
    resolve_agent_log_dir,
    update_runtime_config,
    read_runtime_config,
)

LOG_MODE_ENV_VAR = "SAXOFLOW_AGENT_LOG_MODE"
VALID_MODES = {"off", "summary", "full"}
DEFAULT_MODE = "summary"
SUMMARY_LIMIT = 2400
FULL_LIMIT = 24000
EVENTS_FILENAME = "events.jsonl"
TRANSCRIPT_FILENAME = "transcript.md"

_active_logger: Optional["AgentSessionLogger"] = None


_SECRET_KEY_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd)\b\s*[:=]\s*([^\s,'\"}]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}")
_COMMON_KEY_RE = re.compile(r"\b(?:sk|gsk|ghp|gho|github_pat)_[A-Za-z0-9_]{12,}\b")
_OPENAI_STYLE_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
_SUMMARY_OMIT_KEYS = {
    "prompt",
    "full_prompt",
    "source",
    "source_code",
    "original_code",
    "patched_code",
    "rtl_code",
    "tb_code",
    "file_content",
    "file_contents",
    "diff",
}


def _now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_str(value: Any) -> str:
    plain = getattr(value, "plain", None)
    if isinstance(plain, str):
        return plain

    if isinstance(value, Markdown):
        for attr in ("text", "markdown", "source", "_markdown", "_text"):
            attr_value = getattr(value, attr, None)
            if isinstance(attr_value, str):
                return attr_value
        try:
            candidates = [v for v in vars(value).values() if isinstance(v, str)]
            if candidates:
                return max(candidates, key=len)
        except Exception:
            pass

    if isinstance(value, Panel):
        return _safe_str(getattr(value, "renderable", ""))

    return str(value if value is not None else "")


def renderable_to_text(value: Any) -> str:
    """Return user-readable text from Rich or plain renderables."""
    return _safe_str(value)


def _redact(text: str) -> str:
    value = str(text or "")
    value = _SECRET_KEY_RE.sub(lambda m: f"{m.group(1)}=<redacted>", value)
    value = _BEARER_RE.sub("Bearer <redacted>", value)
    value = _COMMON_KEY_RE.sub("<redacted-token>", value)
    value = _OPENAI_STYLE_RE.sub("<redacted-token>", value)

    for key, secret in os.environ.items():
        upper = key.upper()
        if not any(marker in upper for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            continue
        if secret and len(secret) >= 8:
            value = value.replace(secret, "<redacted-env>")
    return value


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n[truncated {omitted} chars]"


def _sanitize(value: Any, *, mode: str, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            str(k): _sanitize(v, mode=mode, key=str(k).lower())
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(v, mode=mode, key=key) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value

    text = _redact(_safe_str(value))
    if mode != "full" and key in _SUMMARY_OMIT_KEYS:
        return f"[omitted in summary mode: {len(text)} chars]"
    return _truncate(text, FULL_LIMIT if mode == "full" else SUMMARY_LIMIT)


def _load_config_mode() -> str:
    env_mode = os.environ.get(LOG_MODE_ENV_VAR)
    if env_mode:
        return normalize_mode(env_mode)
    cfg_mode = read_runtime_config().get("agent_log_mode")
    if cfg_mode:
        return normalize_mode(str(cfg_mode))
    return DEFAULT_MODE


def normalize_mode(mode: str) -> str:
    """Normalize user-provided log mode to a supported value."""
    cleaned = (mode or "").strip().lower()
    return cleaned if cleaned in VALID_MODES else DEFAULT_MODE


def latest_session_dir(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Return the most recent session directory containing a transcript."""
    root = Path(base_dir) if base_dir else resolve_agent_log_dir(create=False)
    if not root.exists():
        return None
    candidates = [
        path for path in root.iterdir()
        if path.is_dir() and (path / TRANSCRIPT_FILENAME).exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _current_log_root() -> Path:
    """Return the active log root when available, else the resolved root."""
    logger = active_logger()
    if logger and logger.session_dir:
        return logger.session_dir.parent
    return resolve_agent_log_dir(create=False)


def unified_diff_text(before: str, after: str, fromfile: str, tofile: str) -> str:
    """Return a unified diff for full-mode logging."""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


class AgentSessionLogger:
    """Append-only user-facing log writer for one TUI session."""

    def __init__(self, workspace: Path, mode: Optional[str] = None) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.mode = normalize_mode(mode or _load_config_mode())
        self.session_dir: Optional[Path] = None
        self.events_path: Optional[Path] = None
        self.transcript_path: Optional[Path] = None
        self.disabled_reason: Optional[str] = None

        if self.mode != "off":
            self._start_session()

    @property
    def enabled(self) -> bool:
        return self.mode != "off" and self.session_dir is not None

    def set_mode(self, mode: str) -> None:
        self.mode = normalize_mode(mode)
        if self.mode != "off" and self.session_dir is None:
            self._start_session()

    def _start_session(self) -> None:
        """Create session files, disabling logging when storage is unavailable."""
        try:
            root = resolve_agent_log_dir(self.workspace, create=True)
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.session_dir = root / f"{stamp}-{secrets.token_hex(3)}"
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self.events_path = self.session_dir / EVENTS_FILENAME
            self.transcript_path = self.session_dir / TRANSCRIPT_FILENAME
            self._write_header()
            self.disabled_reason = None
        except OSError as exc:
            self.mode = "off"
            self.session_dir = None
            self.events_path = None
            self.transcript_path = None
            self.disabled_reason = str(exc)

    def _write_header(self) -> None:
        if not self.transcript_path:
            return
        header = (
            "# SaxoFlow Agent Session\n\n"
            f"* Started: `{_now_iso()}`\n"
            f"* Workspace: `{self.workspace}`\n"
            f"* Log mode: `{self.mode}`\n\n"
            "This log records the assistant decision trace and user-visible "
            "agent outputs. It does not expose hidden model chain-of-thought.\n\n"
        )
        self.transcript_path.write_text(header, encoding="utf-8")

    def event(
        self,
        kind: str,
        *,
        title: str = "",
        summary: str = "",
        data: Optional[dict] = None,
        full_data: Optional[dict] = None,
    ) -> None:
        if not self.enabled or not self.events_path or not self.transcript_path:
            return

        payload_data = dict(data or {})
        if self.mode == "full" and full_data:
            payload_data.update(full_data)

        payload = {
            "timestamp": _now_iso(),
            "kind": str(kind or "event"),
            "title": str(title or kind or "event"),
            "summary": summary,
            "mode": self.mode,
            "data": _sanitize(payload_data, mode=self.mode),
        }

        try:
            with self.events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            with self.transcript_path.open("a", encoding="utf-8") as fh:
                fh.write(self._markdown_event(payload))
        except OSError as exc:
            self.disabled_reason = str(exc)
            return

    def _markdown_event(self, payload: dict) -> str:
        ts = payload.get("timestamp", "")
        title = payload.get("title") or payload.get("kind") or "event"
        kind = payload.get("kind", "event")
        summary = _redact(str(payload.get("summary") or "")).strip()
        data = payload.get("data") or {}
        lines = [f"## {title}\n\n", f"* Time: `{ts}`\n", f"* Type: `{kind}`\n"]
        if summary:
            lines.extend(["\n", summary, "\n"])
        if data:
            lines.extend(
                [
                    "\n```json\n",
                    json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                    "\n```\n",
                ]
            )
        lines.append("\n")
        return "".join(lines)


def init_session(workspace: Path, mode: Optional[str] = None) -> AgentSessionLogger:
    """Create and activate a logger for the current TUI session."""
    global _active_logger
    _active_logger = AgentSessionLogger(Path(workspace), mode=mode)
    _active_logger.event(
        "session_start",
        title="Session Started",
        summary="SaxoFlow TUI session logging initialized.",
        data={"workspace": str(Path(workspace).resolve())},
    )
    return _active_logger


def active_logger() -> Optional[AgentSessionLogger]:
    """Return the active session logger, if one has been initialized."""
    return _active_logger


def reset_active_logger() -> None:
    """Clear the active logger reference for tests or session teardown."""
    global _active_logger
    _active_logger = None


def log_event(
    kind: str,
    *,
    title: str = "",
    summary: str = "",
    data: Optional[dict] = None,
    full_data: Optional[dict] = None,
) -> None:
    """Append an event to the active session log, if enabled."""
    logger = active_logger()
    if logger is not None:
        logger.event(kind, title=title, summary=summary, data=data, full_data=full_data)


def record_user_turn(user_input: str, panel_kind: str, assistant: Any) -> None:
    """Record a completed visible TUI turn."""
    assistant_text = (
        "[agent transcript displayed]"
        if (user_input or "").strip().lower().startswith("agentlog show")
        else renderable_to_text(assistant)
    )
    log_event(
        "tui_turn",
        title="TUI Turn",
        summary=f"User input routed to `{panel_kind}` panel.",
        data={
            "user": user_input,
            "panel": panel_kind,
            "assistant": assistant_text,
        },
    )


def handle_agentlog_command(command: str) -> Any:
    """Handle TUI `agentlog` utility commands."""
    parts = (command or "").split()
    subcmd = parts[1].lower() if len(parts) > 1 else "path"
    logger = active_logger()

    if subcmd == "path":
        if logger and logger.session_dir:
            return Text(f"Agent session log: {logger.session_dir}", style="cyan")
        if logger and logger.disabled_reason:
            return Text(
                f"Agent logging is unavailable: {logger.disabled_reason}",
                style="yellow",
            )
        mode = _load_config_mode()
        if mode == "off":
            return Text("Agent logging is off. Run `agentlog mode summary` to enable it.", style="yellow")
        path = resolve_agent_log_dir(create=False)
        return Text(f"No active log yet. New sessions will use: {path}", style="yellow")

    if subcmd == "list":
        root = _current_log_root()
        if not root.exists():
            return Text(f"No agent logs found in {root}", style="yellow")
        sessions = sorted(
            [p for p in root.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
        if not sessions:
            return Text(f"No agent logs found in {root}", style="yellow")
        lines = ["Recent agent sessions:"]
        lines.extend(str(path) for path in sessions)
        return Text("\n".join(lines), style="cyan")

    if subcmd == "show":
        session = latest_session_dir(_current_log_root())
        if session is None:
            return Text("No agent session transcript found.", style="yellow")
        transcript = session / TRANSCRIPT_FILENAME
        try:
            text = transcript.read_text(encoding="utf-8")
        except OSError as exc:
            return Text(f"Could not read transcript: {exc}", style="red")
        return Markdown(text)

    if subcmd == "mode":
        if len(parts) < 3:
            mode = logger.mode if logger else _load_config_mode()
            return Text(f"Agent log mode: {mode}", style="cyan")
        mode = normalize_mode(parts[2])
        update_runtime_config({"agent_log_mode": mode})
        if logger:
            logger.set_mode(mode)
        return Text(f"Agent log mode set to: {mode}", style="cyan")

    if subcmd == "dir":
        if len(parts) < 3:
            return Text(f"Agent log directory: {_current_log_root()}", style="cyan")
        path_text = " ".join(parts[2:]).strip()
        path = Path(path_text).expanduser().resolve()
        update_runtime_config({"agent_log_dir": str(path)})
        return Text(
            f"Agent log directory set to: {path}\nNew sessions will use this location.",
            style="cyan",
        )

    return Text(
        "Usage: agentlog path | agentlog list | agentlog show | agentlog mode summary|full|off | agentlog dir <path>",
        style="yellow",
    )
