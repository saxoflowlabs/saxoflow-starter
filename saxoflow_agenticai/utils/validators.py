import re

def is_valid_verilog_syntax(code: str) -> bool:
    """Very basic check for Verilog syntax (not full parser)."""
    return "module" in code and "endmodule" in code

def is_valid_spec(spec: str) -> bool:
    """Check if spec is non-empty and semi-formal."""
    return len(spec.strip()) > 10 and any(kw in spec.lower() for kw in ["input", "output", "clock", "fsm", "state", "logic", "bit"])

def is_safe_input(text: str) -> bool:
    """Avoid malicious prompt injections in agent inputs."""
    forbidden = ["```", "<script", "import os", "rm -rf", "__import__"]
    return not any(f in text.lower() for f in forbidden)
