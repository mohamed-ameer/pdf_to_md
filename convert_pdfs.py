#!/usr/bin/env python3
"""Convert each PDF in a folder to a markdown file with the same name."""

import argparse
import sys
from pathlib import Path

from converter import convert_pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert each PDF to a markdown file in the same folder."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="A PDF file or a folder of PDF files. Default: the current folder.",
    )
    args = parser.parse_args(argv)
    target = Path(args.path).expanduser().resolve()
    pdfs = _pdf_paths(target)
    if not pdfs:
        print(f"No PDF files in {target}", file=sys.stderr)
        return 1
    for pdf in pdfs:
        markdown = convert_pdf(pdf)
        print(f"{pdf.name} -> {markdown.name}")
    return 0


def _pdf_paths(target: Path) -> list[Path]:
    if target.is_file() and target.suffix.lower() == ".pdf":
        return [target]
    if not target.is_dir():
        return []
    return sorted(
        path
        for path in target.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


if __name__ == "__main__":
    raise SystemExit(main())
