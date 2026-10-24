"""Convert a PDF into a markdown file beside it."""

from pathlib import Path

from converter.assemble import build_blocks
from converter.extract import extract_document
from converter.render import render_markdown

__all__ = ["convert_pdf"]


def convert_pdf(pdf_path: Path) -> Path:
    """Write a markdown file for one PDF. Return the markdown path."""
    pdf_path = pdf_path.resolve()
    markdown_path = pdf_path.with_name(pdf_path.stem.strip() + ".md")
    asset_dir = pdf_path.parent / "assets" / _slug(pdf_path.name)
    relative_assets = f"assets/{_slug(pdf_path.name)}"
    document = extract_document(pdf_path, asset_dir, relative_assets)
    blocks = build_blocks(document.lines)
    blocks = _place_figures(blocks, document.figures)
    markdown_path.write_text(render_markdown(blocks, document.source_url), encoding="utf-8")
    if asset_dir.is_dir() and not any(asset_dir.iterdir()):
        asset_dir.rmdir()
    return markdown_path


def _place_figures(blocks: list[dict], figures: list) -> list[dict]:
    events = [(block.get("page", 0), block.get("y", 0), 1, block) for block in blocks]
    for figure in figures:
        events.append((figure.page, figure.y, 0, figure.as_block()))
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    return [event[3] for event in events]


def _slug(filename: str) -> str:
    stem = Path(filename).stem.strip().replace(" ", "-").replace("_", "-")
    cleaned = []
    previous_dash = False
    for char in stem.lower():
        dash = not char.isalnum() and char != "."
        if dash:
            if not previous_dash:
                cleaned.append("-")
            previous_dash = True
            continue
        cleaned.append(char)
        previous_dash = False
    return "".join(cleaned).strip("-")
