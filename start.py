#!/usr/bin/env python3
"""Backward-compatible launcher; prefer running `python3 saxoflow.py`."""

import importlib.util
import sys
from pathlib import Path


def _load_saxoflow_main():
    launcher = Path(__file__).resolve().with_name("saxoflow.py")
    spec = importlib.util.spec_from_file_location("saxoflow_launcher", launcher)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load launcher spec from {launcher}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "main"):
        raise RuntimeError("saxoflow.py does not expose main()")
    return mod.main


main = _load_saxoflow_main()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] Failed to launch via saxoflow.py: {exc}")
        sys.exit(1)
