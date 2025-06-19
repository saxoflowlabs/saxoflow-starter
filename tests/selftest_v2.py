# tests/selftest_v2.py

import os
import sys
import subprocess
import tempfile
import shutil
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def log(msg):
    print(f"[SELFTEST V2] {msg}")

def run(cmd, cwd=None, check=True, env=None):
    log(f"RUN: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if check and result.returncode != 0:
        log(f"❌ Command failed: {result.stderr.strip()}")
        sys.exit(1)
    return result

def setup_sandbox():
    tmpdir = tempfile.mkdtemp(prefix="saxoflow_sandbox_")
    log(f"Sandbox created at: {tmpdir}")
    shutil.copytree(PROJECT_ROOT, os.path.join(tmpdir, "repo"), dirs_exist_ok=True)
    return Path(tmpdir) / "repo"

def create_virtualenv(repo_dir):
    venv_dir = repo_dir / ".venv"
    run([sys.executable, "-m", "venv", str(venv_dir)])
    log("✅ Virtualenv created")
    return venv_dir

def install_package(venv_dir, repo_dir):
    pip_bin = venv_dir / "bin" / "pip"
    run([str(pip_bin), "install", "-e", "."], cwd=repo_dir)
    log("✅ SaxoFlow package installed")

def check_cli_basic(venv_dir):
    python_bin = venv_dir / "bin" / "python"
    run([str(python_bin), "-m", "saxoflow.cli", "--help"])
    log("✅ CLI help works")

def check_doctor(venv_dir):
    saxoflow_bin = venv_dir / "bin" / "saxoflow"
    run([str(saxoflow_bin), "doctor"])
    log("✅ doctor command works")

def run_sandbox_test():
    log("===== SaxoFlow SelfTest V2: FULL SANDBOX =====")
    repo_dir = setup_sandbox()
    venv_dir = create_virtualenv(repo_dir)
    install_package(venv_dir, repo_dir)
    check_cli_basic(venv_dir)
    check_doctor(venv_dir)
    log("===== SELFTEST V2 COMPLETED SUCCESSFULLY =====")

if __name__ == "__main__":
    run_sandbox_test()
