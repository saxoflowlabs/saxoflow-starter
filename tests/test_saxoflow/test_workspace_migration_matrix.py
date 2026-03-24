from __future__ import annotations

import hashlib
import json

import pytest

from saxoflow.workspace.migrate import migrate_legacy_workspace
from saxoflow.workspace.schema import load_project_data, read_selected_tools, workspace_paths
from saxoflow.workspace.validate import validate_workspace


def _contract_fingerprint(root):
	paths = workspace_paths(root)
	payload = b"".join(
		[
			paths.project_file.read_bytes(),
			paths.toolchain_lock_file.read_bytes(),
			paths.models_lock_file.read_bytes(),
		]
	)
	return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
	"legacy_payload,with_legacy_layout,expected_tools,expected_layout,expect_backup",
	[
		(None, False, [], "workspace", False),
		(json.dumps(["yosys", "iverilog", "yosys"]), False, ["iverilog", "yosys"], "workspace", True),
		(json.dumps(["iverilog", "unknown-tool", "iverilog"]), True, ["iverilog", "unknown-tool"], "legacy-unit", True),
		("{broken", True, [], "legacy-unit", True),
	],
)
def test_migrate_legacy_workspace_matrix(
	tmp_path,
	legacy_payload,
	with_legacy_layout,
	expected_tools,
	expected_layout,
	expect_backup,
):
	if with_legacy_layout:
		(tmp_path / "source").mkdir()

	legacy_file = tmp_path / ".saxoflow_tools.json"
	if legacy_payload is not None:
		legacy_file.write_text(legacy_payload, encoding="utf-8")

	first = migrate_legacy_workspace(tmp_path, backup=True)
	second = migrate_legacy_workspace(tmp_path, backup=True)

	# Migration should be stable and re-runnable across representative legacy shapes.
	assert first.migrated is True
	assert second.migrated is True
	assert read_selected_tools(tmp_path) == expected_tools

	project = load_project_data(tmp_path)
	assert project is not None
	assert project["project"]["layout"] == expected_layout

	if expect_backup:
		assert first.backup_file is not None
		assert second.backup_file is not None
	else:
		assert first.backup_file is None
		assert second.backup_file is None

	result = validate_workspace(tmp_path)
	assert result.is_valid is True


def test_migrate_legacy_workspace_is_content_idempotent(tmp_path):
	(tmp_path / "source").mkdir()
	(tmp_path / ".saxoflow_tools.json").write_text(
		json.dumps(["yosys", "iverilog", "unknown-tool"]),
		encoding="utf-8",
	)

	migrate_legacy_workspace(tmp_path, backup=False)
	first_hash = _contract_fingerprint(tmp_path)

	migrate_legacy_workspace(tmp_path, backup=False)
	second_hash = _contract_fingerprint(tmp_path)

	assert first_hash == second_hash
