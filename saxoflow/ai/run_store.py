# saxoflow/ai/run_store.py
"""
M4 AI Command Plane — run record persistence.

Each AI operation writes a small JSON file under
``.saxoflow/ai_runs/<run_id>.json`` so that runs can be resumed,
inspected, or listed after the fact.

Public API
----------
new_run_id()        -> str              12-char hex run identifier
save_run(record, workspace) -> Path     persist record; returns file path
load_run(run_id, workspace) -> record   load by ID (None if not found)
list_runs(workspace)        -> [record] all records sorted by filename
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from saxoflow.ai.contracts import AiLifecycleVerb, AiRunRecord


# Directory relative to workspace root where run records are stored.
_STORE_SUBDIR = ".saxoflow/ai_runs"


# ---------------------------------------------------------------------------
# Run-ID generation
# ---------------------------------------------------------------------------

def new_run_id() -> str:
    """Return a 12-character hex run identifier (collision-resistant)."""
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _store_path(workspace: str) -> Path:
    return Path(workspace) / _STORE_SUBDIR


def _record_to_dict(record: AiRunRecord) -> dict:
    return {
        "run_id": record.run_id,
        "verb": record.verb.value,
        "action": record.action,
        "workspace": record.workspace,
        "started_at": record.started_at,
        "status": record.status,
        "ended_at": record.ended_at,
        "outputs": record.outputs,
        "error": record.error,
    }


def _dict_to_record(data: dict) -> AiRunRecord:
    return AiRunRecord(
        run_id=data["run_id"],
        verb=AiLifecycleVerb(data["verb"]),
        action=data["action"],
        workspace=data["workspace"],
        started_at=data["started_at"],
        status=data["status"],
        ended_at=data.get("ended_at"),
        outputs=data.get("outputs", {}),
        error=data.get("error"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_run(record: AiRunRecord, workspace: str = ".") -> Path:
    """Persist *record* to ``.saxoflow/ai_runs/<run_id>.json``.

    Parameters
    ----------
    record:
        The :class:`~saxoflow.ai.contracts.AiRunRecord` to persist.
    workspace:
        Path to the workspace root (default: current directory).

    Returns
    -------
    Path
        The path to the written JSON file.
    """
    store = _store_path(workspace)
    store.mkdir(parents=True, exist_ok=True)
    fp = store / f"{record.run_id}.json"
    fp.write_text(
        json.dumps(_record_to_dict(record), indent=2),
        encoding="utf-8",
    )
    return fp


def load_run(run_id: str, workspace: str = ".") -> Optional[AiRunRecord]:
    """Load a run record by *run_id*.

    Parameters
    ----------
    run_id:
        The 12-char hex run identifier.
    workspace:
        Path to the workspace root (default: current directory).

    Returns
    -------
    AiRunRecord or None
        The loaded record, or ``None`` if the file does not exist.
    """
    fp = _store_path(workspace) / f"{run_id}.json"
    if not fp.exists():
        return None
    data = json.loads(fp.read_text(encoding="utf-8"))
    return _dict_to_record(data)


def list_runs(workspace: str = ".") -> List[AiRunRecord]:
    """Return all run records sorted by run-ID (file creation order proxy).

    Parameters
    ----------
    workspace:
        Path to the workspace root (default: current directory).

    Returns
    -------
    list[AiRunRecord]
        All records; empty list when no runs exist yet.
    """
    store = _store_path(workspace)
    if not store.exists():
        return []
    records: List[AiRunRecord] = []
    for fp in sorted(store.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            records.append(_dict_to_record(data))
        except Exception:
            # Corrupt records are skipped silently to keep listing stable.
            pass
    return records
