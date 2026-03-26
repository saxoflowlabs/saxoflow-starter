from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from saxoflow.teach._tui_bridge import handle_input
from saxoflow.teach.session import CheckDef, PackDef, StepDef, TeachSession


def _make_session() -> TeachSession:
    step = StepDef(
        id="s1",
        title="Step 1",
        goal="Goal",
        success=[CheckDef(kind="file_exists", file="dummy.txt")],
        hints=["Run the command and verify output."],
    )
    pack = PackDef(
        id="pack",
        name="Pack",
        version="1.0",
        authors=["Test"],
        description="",
        docs=[],
        steps=[step],
        docs_dir=Path("."),
        pack_path=Path("."),
    )
    return TeachSession(pack=pack)


def test_handle_input_teach_next_routes_to_next(monkeypatch):
    session = _make_session()
    calls = {"next": 0}

    def _fake_next(_session, _llm, _verbose):
        calls["next"] += 1
        return Panel("next")

    def _unexpected_tutor(*_args, **_kwargs):
        raise AssertionError("Tutor path should not be used for 'teach next'")

    monkeypatch.setattr("saxoflow.teach._tui_bridge._handle_next", _fake_next)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._handle_tutor_query", _unexpected_tutor)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._render_nav_panel", lambda _s: Panel("nav"))

    handle_input("teach next", session, project_root=".")

    assert calls["next"] == 1


def test_handle_input_teach_prev_routes_to_back(monkeypatch):
    session = _make_session()
    calls = {"back": 0}

    def _fake_back(_session):
        calls["back"] += 1
        return Panel("back")

    def _unexpected_tutor(*_args, **_kwargs):
        raise AssertionError("Tutor path should not be used for 'teach prev'")

    monkeypatch.setattr("saxoflow.teach._tui_bridge._handle_back", _fake_back)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._handle_tutor_query", _unexpected_tutor)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._render_nav_panel", lambda _s: Panel("nav"))

    handle_input("teach prev", session, project_root=".")

    assert calls["back"] == 1


def test_handle_input_teach_check_routes_to_check(monkeypatch):
    session = _make_session()
    calls = {"check": 0}

    def _fake_check(_session, _project_root):
        calls["check"] += 1
        return Panel("check")

    def _unexpected_tutor(*_args, **_kwargs):
        raise AssertionError("Tutor path should not be used for 'teach check'")

    monkeypatch.setattr("saxoflow.teach._tui_bridge._handle_check", _fake_check)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._handle_tutor_query", _unexpected_tutor)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._render_nav_panel", lambda _s: Panel("nav"))

    handle_input("teach check", session, project_root=".")

    assert calls["check"] == 1


def test_handle_input_run_prefers_canonical_action(monkeypatch):
    step = StepDef(
        id="s1",
        title="Step 1",
        goal="Goal",
        canonical_action="saxoflow ai run rtlgen",
        commands=[],
        success=[],
    )
    pack = PackDef(
        id="pack",
        name="Pack",
        version="1.0",
        authors=["Test"],
        description="",
        docs=[],
        steps=[step],
        docs_dir=Path("."),
        pack_path=Path("."),
    )
    session = TeachSession(pack=pack)

    class _RunResult:
        command_str = "saxoflow ai run rtlgen"
        stdout = "ok"
        exit_code = 0
        timed_out = False

    def _fake_run_canonical(_session, _project_root):
        return _RunResult()

    def _fail_run_step_commands(*_args, **_kwargs):
        raise AssertionError("Legacy command path should not be used when canonical_action exists")

    monkeypatch.setattr("saxoflow.teach.runner.run_canonical_action", _fake_run_canonical)
    monkeypatch.setattr("saxoflow.teach.runner.run_step_commands", _fail_run_step_commands)
    monkeypatch.setattr("saxoflow.teach.checks.evaluate_step_success", lambda *_a, **_k: True)
    monkeypatch.setattr("saxoflow.teach._tui_bridge._render_nav_panel", lambda _s: Panel("nav"))

    handle_input("run", session, project_root=".")

    assert session.current_command_index == 1
