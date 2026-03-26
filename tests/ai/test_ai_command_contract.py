# tests/ai/test_ai_command_contract.py
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from saxoflow.ai.contracts import (
    HIGH_IMPACT_ACTIONS,
    AiApprovalPolicy,
    AiLifecycleVerb,
    AiRunRecord,
)
from saxoflow.ai.run_store import list_runs, load_run, new_run_id, now_iso, save_run
from saxoflow.ai.cli import AGENTICAI_CANONICAL_MAP, RUNNABLE_ACTIONS, REVIEW_TYPES, ai_group


class TestContracts:
    def test_verb_values(self):
        assert {v.value for v in AiLifecycleVerb} == {"plan", "run", "resume", "explain", "review"}

    def test_approval_policies(self):
        assert {p.value for p in AiApprovalPolicy} == {"none", "require_flag", "interactive"}

    def test_high_impact_set(self):
        assert "sim" in HIGH_IMPACT_ACTIONS
        assert "fullpipeline" in HIGH_IMPACT_ACTIONS
        assert "rtlgen" not in HIGH_IMPACT_ACTIONS

    def test_run_record_defaults(self):
        rec = AiRunRecord(
            run_id="abc123def456",
            verb=AiLifecycleVerb.RUN,
            action="rtlgen",
            workspace="/tmp/ws",
            started_at="2025-01-01T00:00:00Z",
        )
        assert rec.status == "pending"
        assert rec.outputs == {}
        assert rec.error is None
        assert rec.ended_at is None

    def test_run_record_high_impact(self):
        rec = AiRunRecord(
            run_id="abc123def456",
            verb=AiLifecycleVerb.RUN,
            action="fullpipeline",
            workspace="/tmp/ws",
            started_at="2025-01-01T00:00:00Z",
        )
        assert rec.is_high_impact() is True


class TestRunStore:
    def test_new_run_id_shape(self):
        rid = new_run_id()
        assert len(rid) == 12
        int(rid, 16)

    def test_new_run_id_unique(self):
        assert len({new_run_id() for _ in range(50)}) == 50

    def test_now_iso_has_t(self):
        assert "T" in now_iso()

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        rec = AiRunRecord(
            run_id=new_run_id(),
            verb=AiLifecycleVerb.RUN,
            action="rtlgen",
            workspace=str(tmp_path),
            started_at=now_iso(),
            status="done",
            outputs={"k": "v"},
        )
        fp = save_run(rec, workspace=str(tmp_path))
        assert fp.exists()
        payload = json.loads(fp.read_text(encoding="utf-8"))
        assert payload["outputs"]["k"] == "v"

        loaded = load_run(rec.run_id, workspace=str(tmp_path))
        assert loaded is not None
        assert loaded.run_id == rec.run_id
        assert loaded.verb == AiLifecycleVerb.RUN
        assert loaded.outputs["k"] == "v"

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load_run("missing", workspace=str(tmp_path)) is None

    def test_list_runs(self, tmp_path: Path):
        for action in ["rtlgen", "tbgen"]:
            save_run(
                AiRunRecord(
                    run_id=new_run_id(),
                    verb=AiLifecycleVerb.RUN,
                    action=action,
                    workspace=str(tmp_path),
                    started_at=now_iso(),
                    status="done",
                ),
                workspace=str(tmp_path),
            )
        runs = list_runs(workspace=str(tmp_path))
        assert len(runs) == 2
        assert {r.action for r in runs} == {"rtlgen", "tbgen"}

    def test_list_runs_skips_corrupt_json(self, tmp_path: Path):
        store = tmp_path / ".saxoflow" / "ai_runs"
        store.mkdir(parents=True)
        (store / "bad.json").write_text("not json", encoding="utf-8")
        assert list_runs(workspace=str(tmp_path)) == []


class TestAiCliParsing:
    def test_help_has_all_verbs(self):
        result = CliRunner().invoke(ai_group, ["--help"])
        assert result.exit_code == 0
        for verb in ["plan", "run", "resume", "explain", "review"]:
            assert verb in result.output

    def test_run_invalid_action_rejected(self):
        result = CliRunner().invoke(ai_group, ["run", "bad"])
        assert result.exit_code != 0

    def test_review_invalid_type_rejected(self):
        result = CliRunner().invoke(ai_group, ["review", "--type", "bad"])
        assert result.exit_code != 0


class TestAiCliBehavior:
    def test_run_requires_yes_for_fullpipeline(self):
        result = CliRunner().invoke(ai_group, ["run", "fullpipeline"])
        assert result.exit_code != 0
        assert "--yes" in result.output

    def test_run_requires_yes_for_sim(self):
        result = CliRunner().invoke(ai_group, ["run", "sim"])
        assert result.exit_code != 0

    def test_run_dry_run_creates_record(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["run", "rtlgen", "--dry-run"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower()
        assert len(list_runs(workspace=str(tmp_path))) == 1

    def test_run_success_saves_done_record(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(m, "_dispatch_run", lambda action, **kw: {"status": "done", "output": "ok"})
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["run", "rtlgen"], catch_exceptions=False)
        assert result.exit_code == 0
        runs = list_runs(workspace=str(tmp_path))
        assert len(runs) == 1
        assert runs[0].status == "done"

    def test_run_failure_saves_failed_record(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        def _fail(action, **kw):
            raise RuntimeError("LLM error")

        monkeypatch.setattr(m, "_dispatch_run", _fail)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["run", "rtlgen"])
        assert result.exit_code != 0
        runs = list_runs(workspace=str(tmp_path))
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "LLM error" in (runs[0].error or "")

    def test_plan_creates_record(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["plan", "rtlgen"], catch_exceptions=False)
        assert result.exit_code == 0
        runs = list_runs(workspace=str(tmp_path))
        assert len(runs) == 1
        assert runs[0].verb == AiLifecycleVerb.PLAN

    def test_review_dry_run(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["review", "--type", "rtl", "--dry-run"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_explain_dry_run(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["explain", "--dry-run"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_resume_missing_run_nonzero(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["resume", "badid000000"])
        assert result.exit_code != 0


class TestMappings:
    def test_canonical_map_has_expected_keys(self):
        expected = {
            "rtlgen",
            "tbgen",
            "fpropgen",
            "rtlreview",
            "tbreview",
            "fpropreview",
            "debug",
            "sim",
            "fullpipeline",
            "setupkeys",
            "testllms",
        }
        assert expected.issubset(set(AGENTICAI_CANONICAL_MAP.keys()))

    def test_high_impact_mappings_contain_yes(self):
        assert "--yes" in AGENTICAI_CANONICAL_MAP["sim"]
        assert "--yes" in AGENTICAI_CANONICAL_MAP["fullpipeline"]

    def test_run_action_set(self):
        assert set(RUNNABLE_ACTIONS) == {"rtlgen", "tbgen", "fpropgen", "debug", "sim", "fullpipeline", "report"}

    def test_review_type_set(self):
        assert set(REVIEW_TYPES) == {"rtl", "tb", "formal"}


class TestAiCliInternalHelpers:
    def test_build_plan_text_includes_input_file(self):
        import saxoflow.ai.cli as m

        text = m._build_plan_text("rtlgen", "spec.md")
        assert "Input: spec.md" in text
        assert "Step" in text

    def test_build_plan_text_unknown_target(self):
        import saxoflow.ai.cli as m

        text = m._build_plan_text("custom", None)
        assert "Plan for 'custom'" in text

    def test_build_plan_text_report_target(self):
        import saxoflow.ai.cli as m

        text = m._build_plan_text("report", None)
        assert "gather pipeline artifacts" in text

    def test_dispatch_explain_missing_target_raises(self):
        import saxoflow.ai.cli as m

        with pytest.raises(RuntimeError):
            m._dispatch_explain(None)

    def test_dispatch_run_import_error_path(self, monkeypatch):
        import saxoflow.ai.cli as m

        original = __import__

        def _boom(name, *args, **kwargs):
            if name == "saxoflow_agenticai.cli":
                raise ImportError("missing")
            return original(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _boom)
        with pytest.raises(RuntimeError):
            m._dispatch_run("rtlgen")

    def test_dispatch_review_import_error_path(self, monkeypatch):
        import saxoflow.ai.cli as m

        original = __import__

        def _boom(name, *args, **kwargs):
            if name == "saxoflow_agenticai.cli":
                raise ImportError("missing")
            return original(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _boom)
        with pytest.raises(RuntimeError):
            m._dispatch_review("rtl")

    def test_dispatch_explain_import_error_path(self, monkeypatch):
        import saxoflow.ai.cli as m

        original = __import__

        def _boom(name, *args, **kwargs):
            if name == "saxoflow_agenticai.cli":
                raise ImportError("missing")
            return original(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _boom)
        with pytest.raises(RuntimeError):
            m._dispatch_explain("foo.v")

    def test_dispatch_run_success_and_arg_building(self, monkeypatch):
        import click.testing
        import saxoflow.ai.cli as m

        seen = {}

        def _fake_invoke(self, cli_obj, args, **kwargs):
            seen["args"] = args
            return SimpleNamespace(exit_code=0, output="ok", exception=None)

        monkeypatch.setattr(click.testing.CliRunner, "invoke", _fake_invoke)
        out = m._dispatch_run(
            "sim",
            input_file="in.v",
            output_file="out.v",
            iters=2,
            rtl_file="rtl.v",
            tb_file="tb.v",
            top_module="top",
        )
        assert out["status"] == "done"
        assert seen["args"][0] == "sim"
        assert "--input-file" in seen["args"]
        assert "--output-file" in seen["args"]
        assert "--rtl-file" in seen["args"]
        assert "--tb-file" in seen["args"]
        assert "--top-module" in seen["args"]

    def test_dispatch_run_failure_raises(self, monkeypatch):
        import click.testing
        import saxoflow.ai.cli as m

        def _fake_invoke(self, cli_obj, args, **kwargs):
            return SimpleNamespace(exit_code=1, output="bad", exception=RuntimeError("x"))

        monkeypatch.setattr(click.testing.CliRunner, "invoke", _fake_invoke)
        with pytest.raises(RuntimeError):
            m._dispatch_run("rtlgen")

    def test_dispatch_run_report_delegates_to_report_dispatcher(self, monkeypatch):
        import saxoflow.ai.cli as m

        seen = {}

        def _fake_report(**kwargs):
            seen.update(kwargs)
            return {"status": "done", "report_path": "out.txt"}

        monkeypatch.setattr(m, "_dispatch_report", _fake_report)
        out = m._dispatch_run("report", input_file="spec.md", output_file="out.txt")
        assert out["status"] == "done"
        assert seen == {"input_file": "spec.md", "output_file": "out.txt"}

    def test_dispatch_review_success_and_failure(self, monkeypatch):
        import click.testing
        import saxoflow.ai.cli as m

        def _ok(self, cli_obj, args, **kwargs):
            return SimpleNamespace(exit_code=0, output="ok", exception=None)

        monkeypatch.setattr(click.testing.CliRunner, "invoke", _ok)
        out = m._dispatch_review("formal", input_file="x.sv")
        assert out["status"] == "done"

        def _bad(self, cli_obj, args, **kwargs):
            return SimpleNamespace(exit_code=2, output="err", exception=RuntimeError("err"))

        monkeypatch.setattr(click.testing.CliRunner, "invoke", _bad)
        with pytest.raises(RuntimeError):
            m._dispatch_review("rtl")

    def test_dispatch_explain_success_and_failure(self, monkeypatch):
        import click.testing
        import saxoflow.ai.cli as m

        def _ok(self, cli_obj, args, **kwargs):
            return SimpleNamespace(exit_code=0, output="ok", exception=None)

        monkeypatch.setattr(click.testing.CliRunner, "invoke", _ok)
        out = m._dispatch_explain("a.v")
        assert out["status"] == "done"

        def _bad(self, cli_obj, args, **kwargs):
            return SimpleNamespace(exit_code=1, output="err", exception=RuntimeError("err"))

        monkeypatch.setattr(click.testing.CliRunner, "invoke", _bad)
        with pytest.raises(RuntimeError):
            m._dispatch_explain("a.v")


class TestAiCliSuccessFailureBranches:
    def test_explain_success_non_dry_run(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(m, "_dispatch_explain", lambda target, **kw: {"status": "done", "msg": "ok"})
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["explain", "foo.v"], catch_exceptions=False)
        assert result.exit_code == 0
        runs = list_runs(workspace=str(tmp_path))
        assert runs and runs[0].status == "done"

    def test_explain_failure_non_dry_run(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(m, "_dispatch_explain", lambda target, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["explain", "foo.v"])
        assert result.exit_code != 0
        runs = list_runs(workspace=str(tmp_path))
        assert runs and runs[0].status == "failed"

    def test_review_success_non_dry_run(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(m, "_dispatch_review", lambda t, **kw: {"status": "done"})
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["review", "--type", "tb"], catch_exceptions=False)
        assert result.exit_code == 0
        runs = list_runs(workspace=str(tmp_path))
        assert runs and runs[0].status == "done"

    def test_review_failure_non_dry_run(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(m, "_dispatch_review", lambda t, **kw: (_ for _ in ()).throw(RuntimeError("bad review")))
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(ai_group, ["review", "--type", "tb"])
        assert result.exit_code != 0
        runs = list_runs(workspace=str(tmp_path))
        assert runs and runs[0].status == "failed"

    def test_resume_done_record_prints_yellow_and_returns(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.chdir(tmp_path)
        rec = AiRunRecord(
            run_id="abc123def456",
            verb=AiLifecycleVerb.RUN,
            action="rtlgen",
            workspace=str(tmp_path),
            started_at=now_iso(),
            status="done",
        )
        save_run(rec, workspace=str(tmp_path))
        out = CliRunner().invoke(ai_group, ["resume", "abc123def456"], catch_exceptions=False)
        assert out.exit_code == 0
        assert "already completed" in out.output
        assert "resumed." not in out.output

    def test_resume_pending_record_dispatches(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.chdir(tmp_path)
        rec = AiRunRecord(
            run_id="abc123def457",
            verb=AiLifecycleVerb.RUN,
            action="rtlgen",
            workspace=str(tmp_path),
            started_at=now_iso(),
            status="failed",
            outputs={"_kwargs": {"input_file": "spec.md"}},
        )
        save_run(rec, workspace=str(tmp_path))
        called = []
        monkeypatch.setattr(m, "_dispatch_run", lambda action, **kw: called.append((action, kw)) or {"status": "done"})
        out = CliRunner().invoke(ai_group, ["resume", "abc123def457"], catch_exceptions=False)
        assert out.exit_code == 0
        assert called and called[0][0] == "rtlgen"

    def test_resume_cmd_wraps_runtime_error(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(m, "_dispatch_resume", lambda rid: (_ for _ in ()).throw(RuntimeError("boom")))
        out = CliRunner().invoke(ai_group, ["resume", "abc123def458"])
        assert out.exit_code != 0
        assert "boom" in out.output

    def test_resume_strips_json_suffix_from_run_id(self, tmp_path: Path, monkeypatch):
        """resume abc123.json (copied from ls) should be treated as run_id abc123."""
        import saxoflow.ai.cli as m

        seen_ids = []
        monkeypatch.setattr(m, "_dispatch_resume", lambda rid: seen_ids.append(rid))
        monkeypatch.chdir(tmp_path)
        CliRunner().invoke(ai_group, ["resume", "abc123def459.json"], catch_exceptions=False)
        # _dispatch_resume must receive the id WITHOUT the .json suffix.
        assert seen_ids and seen_ids[0] == "abc123def459"

    def test_run_success_persists_kwargs_for_resume(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(m, "_dispatch_run", lambda action, **kw: {"status": "done", "output": "ok"})
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            ai_group,
            ["run", "report", "--input-file", "spec.md", "--output-file", "output/report/report.txt"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        runs = list_runs(workspace=str(tmp_path))
        assert runs and runs[0].outputs["_kwargs"] == {
            "input_file": "spec.md",
            "output_file": "output/report/report.txt",
            "iters": 1,
        }


class TestAiReportHelpers:
    def test_collect_report_phase_outputs_reads_workspace_artifacts(self, tmp_path: Path):
        import saxoflow.ai.cli as m

        (tmp_path / "source" / "specification").mkdir(parents=True)
        (tmp_path / "source" / "rtl" / "verilog").mkdir(parents=True)
        (tmp_path / "source" / "tb" / "verilog").mkdir(parents=True)
        (tmp_path / "formal").mkdir()
        (tmp_path / "output" / "report").mkdir(parents=True)

        (tmp_path / "source" / "specification" / "unit.md").write_text("SPEC", encoding="utf-8")
        (tmp_path / "source" / "rtl" / "verilog" / "unit.sv").write_text("RTL", encoding="utf-8")
        (tmp_path / "source" / "tb" / "verilog" / "unit_tb.sv").write_text("TB", encoding="utf-8")
        (tmp_path / "formal" / "unit_props.sv").write_text("FORMAL", encoding="utf-8")
        (tmp_path / "output" / "report" / "rtl_review_report.txt").write_text("RTL REVIEW", encoding="utf-8")
        (tmp_path / "output" / "report" / "tb_review_report.txt").write_text("TB REVIEW", encoding="utf-8")
        (tmp_path / "output" / "report" / "fprop_review_report.txt").write_text("FORMAL REVIEW", encoding="utf-8")
        (tmp_path / "output" / "report" / "debug_report.txt").write_text("DEBUG", encoding="utf-8")
        (tmp_path / "output" / "report" / "simulation_status.txt").write_text("success", encoding="utf-8")

        phase_outputs, artifact_paths = m._collect_report_phase_outputs(tmp_path)
        assert phase_outputs["specification"] == "SPEC"
        assert phase_outputs["rtl_code"] == "RTL"
        assert phase_outputs["testbench_code"] == "TB"
        assert phase_outputs["formal_properties"] == "FORMAL"
        assert phase_outputs["rtl_review_report"] == "RTL REVIEW"
        assert phase_outputs["testbench_review_report"] == "TB REVIEW"
        assert phase_outputs["formal_property_review_report"] == "FORMAL REVIEW"
        assert phase_outputs["debug_report"] == "DEBUG"
        assert phase_outputs["simulation_status"] == "success"
        assert artifact_paths["specification"].endswith("unit.md")

    def test_dispatch_report_generates_and_writes_report(self, tmp_path: Path, monkeypatch):
        import saxoflow.ai.cli as m

        captured = {}

        class _FakeReportAgent:
            def run(self, phase_outputs):
                captured["phase_outputs"] = dict(phase_outputs)
                return "PIPELINE SUMMARY"

        def _fake_write_output(content, output_file, default_folder, default_name, ext):
            captured["write"] = {
                "content": content,
                "output_file": output_file,
                "default_folder": str(default_folder),
                "default_name": default_name,
                "ext": ext,
            }
            return tmp_path / "output" / "report" / f"{default_name}{ext}"

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            m,
            "_load_report_dependencies",
            lambda: (_FakeReportAgent, _fake_write_output, lambda path: Path(path).stem),
        )
        monkeypatch.setattr(
            m,
            "_collect_report_phase_outputs",
            lambda workspace, input_file=None: (
                {"specification": "SPEC", "rtl_code": "RTL"},
                {"specification": str(tmp_path / "source" / "specification" / "unit.md")},
            ),
        )

        out = m._dispatch_report(input_file=None, output_file=None)
        assert out["status"] == "done"
        assert out["output"] == "PIPELINE SUMMARY"
        assert out["report_path"].endswith("unit_pipeline_report.txt")
        assert captured["phase_outputs"]["specification"] == "SPEC"
        assert captured["write"]["default_name"] == "unit_pipeline_report"

    def test_dispatch_report_dependency_error_path(self, monkeypatch):
        import saxoflow.ai.cli as m

        monkeypatch.setattr(
            m,
            "_load_report_dependencies",
            lambda: (_ for _ in ()).throw(RuntimeError("deps missing")),
        )
        with pytest.raises(RuntimeError, match="deps missing"):
            m._dispatch_report()
