# tests/teach/test_pack_migration.py
"""Tests for LegacyPackMigrator and MigrationReport.

Covers:
- Happy-path migration of a minimal legacy pack.
- Migration of ethz_ic_design real pack.
- canonical_action inference from agent_invocations.
- canonical_action inference from preferred commands.
- no canonical_action when neither applies.
- grading_safe=True for deterministic-only success checks.
- grading_safe=False for non-deterministic or empty checks.
- Unknown agent_key produces a warning.
- MigrationReport.summary() output.
- Round-trip: migrated spec → to_pack_def() round-trip.
- CLI integrate: teach validate / preview / export via Click test runner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from saxoflow.teach.pack import load_pack
from saxoflow.teach.session import (
    AgentInvocationDef,
    CheckDef,
    CommandDef,
)
from saxoflow.teach.tutorialspec.migrate import LegacyPackMigrator, MigrationReport
from saxoflow.teach.tutorialspec.schema import (
    CANONICAL_ACTION_MAP,
    TUTORIALSPEC_VERSION,
)
from saxoflow.teach.tutorialspec.compiler import TutorialSpecCompiler


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_pack(
    tmp: Path,
    pack_data: dict,
    lessons: dict,
    pack_name: str = "testpack",
) -> Path:
    pack_dir = tmp / pack_name
    (pack_dir / "docs").mkdir(parents=True)
    (pack_dir / "lessons").mkdir(parents=True)

    with open(pack_dir / "pack.yaml", "w") as f:
        yaml.dump(pack_data, f)

    for fname, data in lessons.items():
        with open(pack_dir / "lessons" / fname, "w") as f:
            yaml.dump(data, f)

    return pack_dir


MINIMAL_PACK_DATA = {
    "id": "mini",
    "name": "Mini Pack",
    "version": "1.0",
    "authors": ["Tester"],
    "description": "Minimal pack",
    "docs": [],
    "lessons": ["step1.yaml"],
}

MINIMAL_LESSON = {
    "id": "step1",
    "title": "First Step",
    "goal": "Do something",
    "commands": [{"native": "echo hello"}],
    "success": [],
}


# ---------------------------------------------------------------------------
# MigrationReport
# ---------------------------------------------------------------------------

class TestMigrationReport:
    def test_summary_no_warnings(self):
        report = MigrationReport(
            pack_id="testpack",
            steps_migrated=3,
            steps_with_canonical_action=2,
            steps_grading_safe=1,
        )
        s = report.summary()
        assert "testpack" in s
        assert "3" in s
        assert "Warning" not in s

    def test_summary_with_warnings(self):
        report = MigrationReport(
            pack_id="testpack",
            steps_migrated=1,
            warnings=["step 'x': agent_key 'unknown' not found"],
        )
        s = report.summary()
        assert "Warning" in s
        assert "unknown" in s


# ---------------------------------------------------------------------------
# LegacyPackMigrator — basic path
# ---------------------------------------------------------------------------

class TestLegacyPackMigratorBasic:
    def test_migrate_minimal_pack(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": MINIMAL_LESSON})
        migrator = LegacyPackMigrator()
        spec, report = migrator.migrate(pack_dir)

        assert spec.schema_version == TUTORIALSPEC_VERSION
        assert spec.id == "mini"
        assert len(spec.steps) == 1
        assert report.steps_migrated == 1

    def test_migrate_returns_tutorialspec(self, tmp_path):
        from saxoflow.teach.tutorialspec.schema import TutorialSpec
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": MINIMAL_LESSON})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        assert isinstance(spec, TutorialSpec)

    def test_migrated_step_preserves_id_and_title(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": MINIMAL_LESSON})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].id == "step1"
        assert spec.steps[0].title == "First Step"


# ---------------------------------------------------------------------------
# canonical_action inference
# ---------------------------------------------------------------------------

class TestCanonicalInference:
    @pytest.mark.parametrize("agent_key,expected_suffix", [
        ("rtlgen", "rtlgen"),
        ("tbgen", "tbgen"),
        ("fpropgen", "fpropgen"),
        ("sim", "sim"),
        ("fullpipeline", "fullpipeline"),
    ])
    def test_agent_invocation_infers_canonical(self, tmp_path, agent_key, expected_suffix):
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "agent_invocations": [{"agent_key": agent_key, "description": "run it"}],
            "success": [],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, report = LegacyPackMigrator().migrate(pack_dir)
        step = spec.steps[0]
        assert step.canonical_action is not None
        assert expected_suffix in step.canonical_action
        assert report.steps_with_canonical_action == 1

    def test_preferred_command_infers_canonical(self, tmp_path):
        canonical = CANONICAL_ACTION_MAP["rtlgen"]
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [{"native": "python gen.py", "preferred": canonical}],
            "success": [],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, report = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].canonical_action == canonical

    def test_no_canonical_for_plain_native_command(self, tmp_path):
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [{"native": "make sim"}],
            "success": [],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].canonical_action == "saxoflow teach action run --pack mini --step s1"

    def test_unknown_agent_key_produces_warning(self, tmp_path):
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "agent_invocations": [{"agent_key": "unicorn_agent", "description": ""}],
            "success": [],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, report = LegacyPackMigrator().migrate(pack_dir)
        assert report.warnings
        assert any("unicorn_agent" in w for w in report.warnings)

    @pytest.mark.skipif(
        not (Path(__file__).parents[2] / "packs" / "ethz_ic_design").exists(),
        reason="ethz_ic_design pack not present in workspace",
    )
    def test_fallback_canonical_exists_for_real_pack_steps(self):
        spec, _ = LegacyPackMigrator().migrate(ETHZ_PACK_PATH)
        assert len(spec.steps) > 0
        assert all(s.canonical_action for s in spec.steps)


# ---------------------------------------------------------------------------
# grading_safe inference
# ---------------------------------------------------------------------------

class TestGradingSafeInference:
    def test_grading_safe_for_all_deterministic_checks(self, tmp_path):
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "success": [
                {"kind": "file_exists", "pattern": "out.v"},
                {"kind": "exit_code_0"},
            ],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, report = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].grading_safe is True
        assert report.steps_grading_safe == 1

    def test_not_grading_safe_when_user_confirms(self, tmp_path):
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "success": [{"kind": "user_confirms"}],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].grading_safe is False

    def test_not_grading_safe_when_success_empty(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, success=[])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].grading_safe is False

    def test_mixed_checks_not_grading_safe(self, tmp_path):
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "success": [
                {"kind": "file_exists", "pattern": "out.v"},
                {"kind": "user_confirms"},  # non-deterministic
            ],
        }
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": lesson})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        assert spec.steps[0].grading_safe is False


# ---------------------------------------------------------------------------
# Round-trip: spec → to_pack_def()
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_to_pack_def_is_callable(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": MINIMAL_LESSON})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        pack = spec.to_pack_def()
        assert pack.id == "mini"
        assert len(pack.steps) == 1

    def test_round_trip_step_id_preserved(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": MINIMAL_LESSON})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        pack = spec.to_pack_def()
        assert pack.steps[0].id == "step1"

    def test_round_trip_drops_tutorialspec_fields(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK_DATA, {"step1.yaml": MINIMAL_LESSON})
        spec, _ = LegacyPackMigrator().migrate(pack_dir)
        pack = spec.to_pack_def()
        # canonical_action now exists on StepDef for runtime execution.
        assert hasattr(pack.steps[0], "canonical_action")
        assert pack.steps[0].canonical_action == "saxoflow teach action run --pack mini --step step1"


# ---------------------------------------------------------------------------
# Multi-step pack
# ---------------------------------------------------------------------------

class TestMultiStepPack:
    def _make_multi_lesson(self, step_id: str, agent_key: str | None = None) -> dict:
        lesson: dict = {
            "id": step_id,
            "title": f"Step {step_id}",
            "goal": "Do something",
            "commands": [],
            "success": [{"kind": "file_exists", "pattern": "out.v"}],
        }
        if agent_key:
            lesson["agent_invocations"] = [{"agent_key": agent_key}]
        return lesson

    def test_three_step_pack_all_migrated(self, tmp_path):
        pack_data = dict(MINIMAL_PACK_DATA, lessons=["s1.yaml", "s2.yaml", "s3.yaml"])
        lessons = {
            "s1.yaml": self._make_multi_lesson("s1", agent_key="rtlgen"),
            "s2.yaml": self._make_multi_lesson("s2", agent_key="tbgen"),
            "s3.yaml": self._make_multi_lesson("s3"),
        }
        pack_dir = _write_pack(tmp_path, pack_data, lessons)
        spec, report = LegacyPackMigrator().migrate(pack_dir)

        assert report.steps_migrated == 3
        assert report.steps_with_canonical_action == 3
        assert report.steps_grading_safe == 3  # all have file_exists

    def test_compiler_accepts_migrated_multi_step_spec(self, tmp_path):
        pack_data = dict(MINIMAL_PACK_DATA, lessons=["s1.yaml", "s2.yaml"])
        lessons = {
            "s1.yaml": self._make_multi_lesson("s1", agent_key="rtlgen"),
            "s2.yaml": self._make_multi_lesson("s2"),
        }
        pack_dir = _write_pack(tmp_path, pack_data, lessons)
        spec, _ = LegacyPackMigrator().migrate(pack_dir)

        result = TutorialSpecCompiler().compile(spec)
        assert result.ok, f"Expected OK but got: {result.summary()}"


# ---------------------------------------------------------------------------
# Real pack: ethz_ic_design
# ---------------------------------------------------------------------------

ETHZ_PACK_PATH = Path(__file__).parents[2] / "packs" / "ethz_ic_design"


@pytest.mark.skipif(
    not ETHZ_PACK_PATH.exists(),
    reason="ethz_ic_design pack not present in workspace",
)
class TestEthzPackMigration:
    """Smoke tests against the real ethz_ic_design teaching pack."""

    def test_ethz_pack_migrates_without_error(self):
        spec, report = LegacyPackMigrator().migrate(ETHZ_PACK_PATH)
        assert spec is not None
        assert report.steps_migrated > 0

    def test_ethz_pack_schema_version(self):
        spec, _ = LegacyPackMigrator().migrate(ETHZ_PACK_PATH)
        assert spec.schema_version == TUTORIALSPEC_VERSION

    def test_ethz_pack_compiles_ok(self):
        spec, _ = LegacyPackMigrator().migrate(ETHZ_PACK_PATH)
        result = TutorialSpecCompiler().compile(spec)
        assert result.ok, (
            f"ethz_ic_design failed validation:\n"
            + "\n".join(f"  [{i.severity}] step={i.step_id}: {i.message}" for i in result.issues)
        )

    def test_ethz_pack_has_steps(self):
        spec, _ = LegacyPackMigrator().migrate(ETHZ_PACK_PATH)
        assert len(spec.steps) >= 1

    def test_ethz_pack_to_pack_def_roundtrip(self):
        spec, _ = LegacyPackMigrator().migrate(ETHZ_PACK_PATH)
        pack = spec.to_pack_def()
        assert pack.id == spec.id
        assert len(pack.steps) == len(spec.steps)


# ---------------------------------------------------------------------------
# CLI command tests (teach validate / preview / export)
# ---------------------------------------------------------------------------

class TestTeachCLICommands:
    """Integration tests: Click runner invokes the teach validate/preview/export."""

    def _make_cli_pack(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create a minimal pack and return (packs_dir, pack_dir)."""
        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "Run RTL",
            "goal": "Generate RTL",
            "commands": [],
            "agent_invocations": [{"agent_key": "rtlgen"}],
            "success": [{"kind": "file_exists", "pattern": "out.v"}],
        }
        pack_data = {
            "id": "clipack",
            "name": "CLI Pack",
            "version": "1.0",
            "authors": ["Test"],
            "description": "For CLI tests",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        pack_dir = _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="clipack")
        return packs_dir, pack_dir

    def test_teach_validate_ok(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_validate

        packs_dir, _ = self._make_cli_pack(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            teach_validate,
            ["clipack", "--packs-dir", str(packs_dir)],
        )
        assert result.exit_code == 0, result.output
        assert "[M5 transition shim]" in result.output
        assert "OK" in result.output

    def test_teach_validate_missing_pack_exits_1(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_validate

        runner = CliRunner()
        result = runner.invoke(
            teach_validate,
            ["no_such_pack", "--packs-dir", str(tmp_path)],
        )
        assert result.exit_code == 1

    def test_teach_preview_shows_step_info(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_preview

        packs_dir, _ = self._make_cli_pack(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            teach_preview,
            ["clipack", "--packs-dir", str(packs_dir), "--step", "0"],
        )
        assert result.exit_code == 0, result.output
        assert "[M5 transition shim]" in result.output
        assert "Run RTL" in result.output

    def test_teach_export_creates_json(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_export

        packs_dir, _ = self._make_cli_pack(tmp_path)
        out_dir = tmp_path / "export_out"

        runner = CliRunner()
        result = runner.invoke(
            teach_export,
            ["clipack", "--packs-dir", str(packs_dir), "--output-dir", str(out_dir)],
        )
        assert result.exit_code == 0, result.output
        assert "[M5 transition shim]" in result.output

        out_file = out_dir / "clipack_grading.json"
        assert out_file.exists()

        data = json.loads(out_file.read_text())
        assert data["pack_id"] == "clipack"
        assert len(data["grading_steps"]) >= 1
        assert data["grading_steps"][0]["id"] == "s1"

    def test_teach_export_no_grading_safe_steps(self, tmp_path):
        """Export with no grading-safe steps prints a message and exits 0."""
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_export

        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "success": [{"kind": "user_confirms"}],  # non-deterministic → not grading_safe
        }
        pack_data = {
            "id": "nograde",
            "name": "NoGrade Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="nograde")

        runner = CliRunner()
        result = runner.invoke(
            teach_export,
            ["nograde", "--packs-dir", str(packs_dir)],
        )
        assert result.exit_code == 0
        assert "No grading-safe" in result.output

    def test_teach_import_legacy_pack_writes_tutorialspec(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_import

        packs_dir, pack_dir = self._make_cli_pack(tmp_path)
        out_spec = tmp_path / "clipack.tutorialspec.yaml"

        runner = CliRunner()
        result = runner.invoke(
            teach_import,
            [str(pack_dir), "--output", str(out_spec)],
        )

        assert result.exit_code == 0, result.output
        assert out_spec.exists()
        assert "[M5 transition shim]" in result.output
        assert "Imported legacy pack" in result.output

    def test_teach_build_compiles_pack_with_canonical_action(self, tmp_path):
        from click.testing import CliRunner
        import yaml
        from saxoflow.teach.cli import teach_build

        spec = {
            "schema_version": "1.0",
            "id": "builtpack",
            "name": "Built Pack",
            "version": "1.0",
            "authors": ["Test"],
            "description": "Built from tutorialspec",
            "docs": [],
            "steps": [
                {
                    "id": "s1",
                    "title": "S1",
                    "goal": "G1",
                    "canonical_action": "saxoflow ai run rtlgen",
                    "commands": [],
                    "success": [{"kind": "file_exists", "pattern": "out.v"}],
                }
            ],
        }
        spec_path = tmp_path / "builtpack.tutorialspec.yaml"
        spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

        out_dir = tmp_path / "packs_out"
        runner = CliRunner()
        result = runner.invoke(
            teach_build,
            [str(spec_path), "--output-dir", str(out_dir)],
        )
        assert result.exit_code == 0, result.output

        built_pack = out_dir / "builtpack"
        assert (built_pack / "pack.yaml").exists()
        lesson = yaml.safe_load((built_pack / "lessons" / "01_s1.yaml").read_text(encoding="utf-8"))
        assert lesson["canonical_action"] == "saxoflow ai run rtlgen"

    def test_teach_build_output_can_be_loaded_by_pack_loader(self, tmp_path):
        from click.testing import CliRunner
        import yaml
        from saxoflow.teach.cli import teach_build
        from saxoflow.teach.pack import load_pack

        spec = {
            "schema_version": "1.0",
            "id": "loadablepack",
            "name": "Loadable Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "steps": [
                {
                    "id": "s1",
                    "title": "S1",
                    "goal": "G1",
                    "canonical_action": "saxoflow ai run rtlgen",
                    "commands": [],
                    "success": [],
                }
            ],
        }
        spec_path = tmp_path / "loadable.tutorialspec.yaml"
        spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
        out_dir = tmp_path / "packs_out"

        runner = CliRunner()
        result = runner.invoke(
            teach_build,
            [str(spec_path), "--output-dir", str(out_dir)],
        )
        assert result.exit_code == 0, result.output

        pack = load_pack(out_dir / "loadablepack")
        assert len(pack.steps) == 1
        assert pack.steps[0].canonical_action == "saxoflow ai run rtlgen"

    def test_teach_action_run_executes_step(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_action_run

        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [{"native": "echo hello"}],
            "success": [{"kind": "always"}],
        }
        pack_data = {
            "id": "actionpack",
            "name": "Action Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="actionpack")

        runner = CliRunner()
        result = runner.invoke(
            teach_action_run,
            [
                "--pack", "actionpack",
                "--step", "s1",
                "--packs-dir", str(packs_dir),
                "--project-root", str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "$ echo hello" in result.output

    def test_teach_publish_copies_pack_and_manifest(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_publish

        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "canonical_action": "saxoflow teach action run --pack pubpack --step s1",
            "commands": [],
            "success": [],
        }
        pack_data = {
            "id": "pubpack",
            "name": "Publish Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        pack_dir = _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="pubpack")
        (pack_dir / "tutorialspec.build.json").write_text("{}", encoding="utf-8")

        registry_dir = tmp_path / "registry"
        runner = CliRunner()
        result = runner.invoke(
            teach_publish,
            ["pubpack", "--packs-dir", str(packs_dir), "--registry-dir", str(registry_dir)],
        )
        assert result.exit_code == 0, result.output
        assert (registry_dir / "pubpack" / "pack.yaml").exists()
        manifest_path = registry_dir / "pubpack" / "publish.manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["build_manifest_present"] is True
        assert manifest["canonical_steps"] == 1
        assert manifest["total_steps"] == 1

    def test_teach_publish_fails_without_build_manifest_by_default(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_publish

        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "canonical_action": "saxoflow teach action run --pack pubpack --step s1",
            "commands": [],
            "success": [],
        }
        pack_data = {
            "id": "pubpack",
            "name": "Publish Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="pubpack")

        registry_dir = tmp_path / "registry"
        runner = CliRunner()
        result = runner.invoke(
            teach_publish,
            ["pubpack", "--packs-dir", str(packs_dir), "--registry-dir", str(registry_dir)],
        )
        assert result.exit_code == 1
        assert "missing tutorialspec.build.json" in result.output

    def test_teach_publish_fails_when_canonical_incomplete_by_default(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_publish

        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "success": [],
        }
        pack_data = {
            "id": "pubpack",
            "name": "Publish Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        pack_dir = _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="pubpack")
        (pack_dir / "tutorialspec.build.json").write_text("{}", encoding="utf-8")

        registry_dir = tmp_path / "registry"
        runner = CliRunner()
        result = runner.invoke(
            teach_publish,
            ["pubpack", "--packs-dir", str(packs_dir), "--registry-dir", str(registry_dir)],
        )
        assert result.exit_code == 1
        assert "canonical coverage is incomplete" in result.output

    def test_teach_publish_can_opt_out_of_strict_publish_checks(self, tmp_path):
        from click.testing import CliRunner
        from saxoflow.teach.cli import teach_publish

        packs_dir = tmp_path / "packs"
        lesson = {
            "id": "s1",
            "title": "T",
            "goal": "G",
            "commands": [],
            "success": [],
        }
        pack_data = {
            "id": "pubpack",
            "name": "Publish Pack",
            "version": "1.0",
            "authors": [],
            "description": "",
            "docs": [],
            "lessons": ["s1.yaml"],
        }
        _write_pack(packs_dir, pack_data, {"s1.yaml": lesson}, pack_name="pubpack")

        registry_dir = tmp_path / "registry"
        runner = CliRunner()
        result = runner.invoke(
            teach_publish,
            [
                "pubpack",
                "--packs-dir", str(packs_dir),
                "--registry-dir", str(registry_dir),
                "--no-require-build-manifest",
                "--allow-native-fallback",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (registry_dir / "pubpack" / "publish.manifest.json").exists()


# ---------------------------------------------------------------------------
# is_canonical_available from command_map
# ---------------------------------------------------------------------------

class TestIsCanonicalAvailable:
    def test_available_when_executable_on_path(self):
        from saxoflow.teach import command_map as cm
        from unittest.mock import patch

        with patch.object(cm, "_availability_checker", lambda cmd: True):
            assert cm.is_canonical_available("saxoflow ai run rtlgen") is True

    def test_not_available_when_executable_missing(self):
        from saxoflow.teach import command_map as cm
        from unittest.mock import patch

        with patch.object(cm, "_availability_checker", lambda cmd: False):
            assert cm.is_canonical_available("saxoflow ai run rtlgen") is False

    def test_empty_string_returns_false(self):
        from saxoflow.teach.command_map import is_canonical_available
        assert is_canonical_available("") is False


# ---------------------------------------------------------------------------
# run_canonical_action from runner
# ---------------------------------------------------------------------------

class TestRunCanonicalAction:
    """Unit tests for runner.run_canonical_action (M5 canonical execution path)."""

    def _make_session(self, canonical_action=None):
        from saxoflow.teach.session import (
            PackDef, StepDef, TeachSession,
        )
        from saxoflow.teach.tutorialspec.schema import TutorialStep
        from pathlib import Path

        if canonical_action is not None:
            step = TutorialStep(
                id="s1",
                title="T",
                goal="G",
                canonical_action=canonical_action,
            )
        else:
            step = StepDef(id="s1", title="T", goal="G")

        pack = PackDef(
            id="p",
            name="P",
            version="1.0",
            authors=[],
            description="",
            docs=[],
            steps=[step],
            docs_dir=Path("/tmp"),
            pack_path=Path("/tmp"),
        )
        return TeachSession(pack=pack)

    def test_returns_none_for_step_without_canonical_action(self, tmp_path):
        from saxoflow.teach.runner import run_canonical_action

        session = self._make_session(canonical_action=None)
        result = run_canonical_action(session, tmp_path)
        assert result is None

    def test_returns_none_when_legacy_stepdef_no_attr(self, tmp_path):
        """Legacy StepDef has no canonical_action → runner falls back gracefully."""
        from saxoflow.teach.runner import run_canonical_action

        session = self._make_session(canonical_action=None)
        # Force a plain StepDef (no canonical_action attribute at all)
        result = run_canonical_action(session, tmp_path)
        assert result is None

    def test_returns_none_when_no_current_step(self, tmp_path):
        from saxoflow.teach.runner import run_canonical_action
        from saxoflow.teach.session import PackDef, TeachSession

        pack = PackDef(
            id="p", name="P", version="1.0", authors=[],
            description="", docs=[], steps=[],
            docs_dir=tmp_path, pack_path=tmp_path,
        )
        session = TeachSession(pack=pack)
        result = run_canonical_action(session, tmp_path)
        assert result is None

    def test_returns_none_when_executable_not_found(self, tmp_path):
        """canonical_action set but executable not on PATH → None + warning logged."""
        from unittest.mock import patch
        from saxoflow.teach.runner import run_canonical_action

        session = self._make_session(canonical_action="nonexistent_binary_xyz --run")
        with patch("shutil.which", return_value=None):
            result = run_canonical_action(session, tmp_path)
        assert result is None

    def test_executes_canonical_when_executable_found(self, tmp_path):
        """When executable is on PATH, canonical action is executed."""
        from unittest.mock import patch
        from saxoflow.teach.runner import run_canonical_action, RunResult

        session = self._make_session(canonical_action="echo test_canonical_run")
        # echo is always available but we patch _execute_single to avoid subprocess
        mock_result = RunResult(
            command_str="echo test_canonical_run",
            stdout="test_canonical_run",
            exit_code=0,
        )
        with patch("saxoflow.teach.runner._execute_single", return_value=mock_result), \
             patch("shutil.which", return_value="/usr/bin/echo"):
            result = run_canonical_action(session, tmp_path)

        assert result is not None
        assert result.exit_code == 0
        assert session.last_run_exit_code == 0
        assert session.last_run_command == "echo test_canonical_run"
