def trim_code_block(code: str) -> str:
    """Remove excessive empty lines and trailing spaces from code blocks."""
    lines = [line.rstrip() for line in code.strip().splitlines()]
    return "\n".join(line for line in lines if line.strip() != "")

def highlight_keywords(text: str, keywords: list) -> str:
    """Add emphasis markers around keywords for better display (e.g., **keyword**)."""
    for keyword in keywords:
        text = text.replace(keyword, f"**{keyword}**")
    return text

def truncate_output(text: str, max_lines: int = 30) -> str:
    """Truncate long outputs for cleaner CLI previews."""
    lines = text.strip().splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + "\n... (truncated)"
    return text
