from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_command_parity.py"
    spec = importlib.util.spec_from_file_location("check_command_parity", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_parity_script_reports_no_findings():
    module = _load_script_module()
    findings = module.run_checks()
    assert findings == []
