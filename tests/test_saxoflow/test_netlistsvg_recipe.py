"""Hermetic checks for the NetlistSVG installer recipe."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RECIPE = REPO_ROOT / "scripts/recipes/netlistsvg.sh"


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_netlistsvg_recipe_reuses_nvm_and_accepts_help_exit_one(tmp_path):
    home = tmp_path / "home"
    fake_path = tmp_path / "path"
    fake_path.mkdir()
    for command in (
        "bash",
        "basename",
        "cat",
        "chmod",
        "date",
        "dirname",
        "find",
        "grep",
        "ln",
        "mkdir",
        "sort",
        "tail",
        "tee",
        "touch",
    ):
        target = shutil.which(command)
        assert target is not None
        (fake_path / command).symlink_to(target)

    nvm_bin = home / ".nvm/versions/node/v22.21.1/bin"
    _write_executable(nvm_bin / "node", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        nvm_bin / "npm",
        """#!/usr/bin/env bash
set -e
prefix=""
while [[ "$#" -gt 0 ]]; do
  if [[ "$1" == "--prefix" ]]; then
    prefix="$2"
    shift 2
  else
    shift
  fi
done
mkdir -p "$prefix/node_modules/.bin"
cat > "$prefix/node_modules/.bin/netlistsvg" <<'EOF'
#!/usr/bin/env bash
echo "usage: netlistsvg input_json_file [-o output_svg_file]"
exit 1
EOF
chmod +x "$prefix/node_modules/.bin/netlistsvg"
""",
    )

    env = os.environ.copy()
    env.pop("NVM_DIR", None)
    env.update(
        {
            "HOME": str(home),
            "PATH": str(fake_path),
            "SHELL": "/bin/bash",
        }
    )
    result = subprocess.run(
        ["bash", str(RECIPE)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "Using Node.js from NVM" in result.stdout
    assert "Updating APT package index" not in result.stdout
    binary = home / ".local/netlistsvg/bin/netlistsvg"
    assert binary.is_symlink()
    assert "NetlistSVG installed" in result.stdout


def test_netlistsvg_recipe_uses_real_ubuntu_package_names():
    source = RECIPE.read_text(encoding="utf-8")

    assert "check_deps nodejs npm" in source
    assert "check_deps node npm" not in source
