from __future__ import annotations

import json

from rich.markdown import Markdown
from rich.text import Text


def test_summary_log_creates_jsonl_and_transcript_with_redaction(tmp_path, monkeypatch):
    from cool_cli import agent_session_log as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SAXOFLOW_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("SAXOFLOW_AGENT_LOG_MODE", raising=False)
    monkeypatch.delenv("SAXOFLOW_AGENT_LOG_DIR", raising=False)
    sut.reset_active_logger()

    logger = sut.init_session(workspace)
    sut.log_event(
        "llm_call",
        title="LLM Call",
        summary="Called model with redacted context.",
        data={
            "prompt": "OPENAI_API_KEY=sk-testsecret123456789",
            "message": "visible response",
        },
    )

    assert logger.session_dir is not None
    assert logger.events_path is not None
    assert logger.transcript_path is not None
    assert logger.session_dir.parent == workspace / ".saxoflow" / "agent_sessions"

    events = [
        json.loads(line)
        for line in logger.events_path.read_text(encoding="utf-8").splitlines()
    ]
    event = events[-1]
    assert event["kind"] == "llm_call"
    assert event["data"]["prompt"].startswith("[omitted in summary mode:")
    assert event["data"]["message"] == "visible response"

    transcript = logger.transcript_path.read_text(encoding="utf-8")
    assert "hidden model chain-of-thought" in transcript
    assert "sk-testsecret" not in transcript


def test_full_mode_keeps_full_fields_with_redaction(tmp_path, monkeypatch):
    from cool_cli import agent_session_log as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SAXOFLOW_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SAXOFLOW_AGENT_LOG_MODE", "full")
    sut.reset_active_logger()

    logger = sut.init_session(workspace)
    sut.log_event(
        "edit",
        title="Edit",
        data={"prompt": "token=abc1234567890 keep code", "diff": "+module x; endmodule"},
    )

    assert logger.events_path is not None
    events = [
        json.loads(line)
        for line in logger.events_path.read_text(encoding="utf-8").splitlines()
    ]
    event = events[-1]
    assert event["mode"] == "full"
    assert event["data"]["prompt"] == "token=<redacted> keep code"
    assert event["data"]["diff"] == "+module x; endmodule"


def test_off_mode_writes_no_session_files(tmp_path, monkeypatch):
    from cool_cli import agent_session_log as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SAXOFLOW_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SAXOFLOW_AGENT_LOG_MODE", "off")
    sut.reset_active_logger()

    logger = sut.init_session(workspace)
    sut.log_event("chat", title="Chat", data={"message": "hello"})

    assert logger.enabled is False
    assert logger.session_dir is None
    assert not (workspace / ".saxoflow" / "agent_sessions").exists()


def test_unwritable_log_storage_disables_logging_without_aborting(tmp_path, monkeypatch):
    from cool_cli import agent_session_log as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SAXOFLOW_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("SAXOFLOW_AGENT_LOG_MODE", raising=False)
    monkeypatch.setattr(
        sut,
        "resolve_agent_log_dir",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read-only storage")),
    )
    sut.reset_active_logger()

    logger = sut.init_session(workspace)
    result = sut.handle_agentlog_command("agentlog path")

    assert logger.enabled is False
    assert logger.mode == "off"
    assert logger.disabled_reason == "read-only storage"
    assert isinstance(result, Text)
    assert "read-only storage" in result.plain


def test_agentlog_commands_show_path_list_and_mode(tmp_path, monkeypatch):
    from cool_cli import agent_session_log as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SAXOFLOW_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("SAXOFLOW_AGENT_LOG_MODE", raising=False)
    sut.reset_active_logger()

    logger = sut.init_session(workspace)
    path_result = sut.handle_agentlog_command("agentlog path")
    list_result = sut.handle_agentlog_command("agentlog list")
    show_result = sut.handle_agentlog_command("agentlog show")
    mode_result = sut.handle_agentlog_command("agentlog mode full")
    dir_result = sut.handle_agentlog_command(f"agentlog dir {tmp_path / 'next_logs'}")

    assert isinstance(path_result, Text)
    assert str(logger.session_dir) in path_result.plain
    assert isinstance(list_result, Text)
    assert str(logger.session_dir) in list_result.plain
    assert isinstance(show_result, Markdown)
    assert isinstance(mode_result, Text)
    assert "full" in mode_result.plain
    assert sut.active_logger() is not None
    assert sut.active_logger().mode == "full"
    assert isinstance(dir_result, Text)
    assert "next_logs" in dir_result.plain


def test_custom_agent_log_dir_env_override(tmp_path, monkeypatch):
    from cool_cli import agent_session_log as log_sut
    from saxoflow import runtime_paths as path_sut

    custom = tmp_path / "custom_logs"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SAXOFLOW_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SAXOFLOW_AGENT_LOG_DIR", str(custom))
    monkeypatch.delenv("SAXOFLOW_AGENT_LOG_MODE", raising=False)
    log_sut.reset_active_logger()

    logger = log_sut.init_session(workspace)

    assert path_sut.resolve_agent_log_dir(workspace) == custom
    assert logger.session_dir is not None
    assert logger.session_dir.parent == custom
