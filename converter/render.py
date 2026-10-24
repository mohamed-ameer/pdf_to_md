"""Render document blocks as markdown."""

import re


def render_markdown(blocks: list[dict], source_url: str | None) -> str:
    pieces: list[str] = []
    previous = None
    source_added = False
    for block in blocks:
        piece = _render_block(block)
        if not piece:
            continue
        if pieces and previous == "item" and block["type"] == "item":
            pieces.append("\n" + piece)
        else:
            pieces.append(("\n\n" if pieces else "") + piece)
        if block["type"] == "heading" and block.get("level") == "h1" and source_url and not source_added:
            pieces.append(f"\n\nSource: {source_url}")
            source_added = True
        previous = block["type"]
    text = "".join(pieces).strip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", text)


def _render_block(block: dict) -> str:
    kind = block["type"]
    if kind == "heading":
        level = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}[block["level"]]
        return f"{level} {block['text'].strip()}"
    if kind == "paragraph":
        return block["text"].strip()
    if kind == "caption":
        return "*" + block["text"].strip() + "*"
    if kind == "item":
        return _render_item(block)
    if kind == "code":
        return _render_code(block)
    if kind == "table":
        return _render_table(block["rows"])
    if kind == "image":
        return f"![{block['alt']}]({block['path']})"
    return ""


def _render_item(block: dict) -> str:
    indent = "  " * (block["level"] - 1)
    text = block["text"].strip()
    if block["ordered"]:
        number = re.match(r"^(\d+)\.", text)
        prefix = f"{number.group(1)}. " if number else "1. "
        text = re.sub(r"^\d+\.\s+", "", text)
    else:
        prefix = "- "
    return f"{indent}{prefix}{text}"


def _render_code(block: dict) -> str:
    code = "\n".join(block["lines"]).strip("\n")
    if not code.strip():
        return ""
    fence = "````" if "```" in code else "```"
    return f"{fence}{_code_language(code)}\n{code}\n{fence}"


def _render_table(rows: list[list[str]]) -> str:
    width = max(len(row) for row in rows)
    body = [[_cell(row[index] if index < len(row) else "") for index in range(width)] for row in rows]
    lines = [
        "| " + " | ".join(body[0]) + " |",
        "| " + " | ".join("---" for _ in body[0]) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body[1:])
    return "\n".join(lines)


def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().replace("|", "\\|")


def _code_language(code: str) -> str:
    sample = "\n".join(code.splitlines()[:12])
    if re.search(r"^\s*(def |import |from |class )", sample, re.M) or "PasswordHasher" in sample:
        return "python"
    if "module.exports" in sample or re.search(r"^\s*(const|let|function)\s", sample, re.M):
        return "javascript"
    if sample.strip().startswith("{") or re.search(r'^\s*"[^"]+"\s*:', sample, re.M):
        return "json"
    if re.search(r"^\s*(repos:|exclude:|hooks:|default_install_hook_types:)", sample, re.M):
        return "yaml"
    if re.search(r"^\s*(docker|git |cd |chmod |cp |nano |npm |yarn |bench )", sample, re.M):
        return "bash"
    if any(char in sample for char in "┌│└"):
        return "text"
    return ""
