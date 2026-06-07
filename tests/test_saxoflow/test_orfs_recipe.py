"""Static safety and reproducibility checks for the ORFS installer recipe."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RECIPE = REPO_ROOT / "scripts/recipes/orfs.sh"


def test_orfs_recipe_has_valid_shell_syntax():
    result = subprocess.run(
        ["bash", "-n", str(RECIPE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_orfs_recipe_is_pinned_resumable_and_reuses_openroad():
    source = RECIPE.read_text(encoding="utf-8")

    assert "eb14d768b6c34cf4f8c5177f3531422b94cf2544" in source
    assert "49bd051a10f0dd5bb89eba9acf668e8362b883d8" in source
    assert 'TEMP_ROOT="$ORFS_ROOT/.install-$ORFS_REVISION"' in source
    assert "Resuming the partial ORFS checkout" in source
    assert "sha256sum" in source
    assert ".saxoflow-install.json" in source
    assert "sparse-checkout init --no-cone" in source
    assert "!/flow/platforms/*/" in source
    assert "submodule update --init --recursive" not in source
    assert "At least 2 GB" in source
    assert "saxoflow install openroad" in source
    assert "Installing another OpenROAD" not in source
    assert os.access(RECIPE, os.X_OK)
