"""Read PDF lines, figures, and the source link."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

HEADING_SIZES = ((24, "h1"), (19, "h2"), (15, "h3"), (13, "h4"))
BOX_DRAWING = "│┌┐└┘├┤┬┴┼─▼▲◄►"


@dataclass
class Line:
    page: int
    y: float
    x: float
    x1: float
    y1: float
    size: float
    text: str
    kind: str
    bullet: bool = False
    ordered: bool = False


@dataclass
class Figure:
    page: int
    y: float
    path: str
    alt: str

    def as_block(self) -> dict:
        return {
            "type": "image",
            "path": self.path,
            "alt": self.alt,
            "page": self.page,
            "y": self.y,
        }


@dataclass
class Document:
    lines: list[Line] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    source_url: str | None = None


def extract_document(pdf_path: Path, asset_dir: Path, relative_assets: str) -> Document:
    document = pymupdf.open(pdf_path)
    extracted = Document(source_url=_source_url(document))
    extracted.lines = _merge_code_gutters(_read_lines(document))
    _demote_isolated_code(extracted.lines)
    extracted.figures = _read_figures(document, asset_dir, relative_assets)
    _replace_diagrams(document, extracted, asset_dir, relative_assets)
    document.close()
    return extracted


def _read_lines(document: pymupdf.Document) -> list[Line]:
    lines: list[Line] = []
    for page_index, page in enumerate(document):
        bullets = _bullet_marks(page)
        links = [link for link in page.get_links() if link.get("uri")]
        page_lines = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for raw_line in block["lines"]:
                parsed = _parse_line(raw_line, links, bullets, page_index)
                if parsed is not None:
                    page_lines.append(parsed)
        page_lines.sort(key=lambda item: (item.y, item.x))
        lines.extend(page_lines)
    return lines


def _parse_line(raw_line: dict, links: list, bullets: list, page_index: int) -> Line | None:
    spans = raw_line["spans"]
    if not spans:
        return None
    plain = "".join(span["text"] for span in spans)
    size = max(span["size"] for span in spans)
    fonts = " ".join(span["font"] for span in spans)
    if _is_footer(raw_line["bbox"][1], size, fonts, plain):
        return None
    markdown, ratio = _render_spans(spans, links)
    kind, text = _classify(size, plain, ratio, spans)
    if plain.strip().startswith("Contribution by"):
        kind = "body"
        text = plain.strip()
        markdown = text
    if kind != "code" and not text:
        return None
    x0, y0, x1, y1 = raw_line["bbox"]
    line = Line(
        page=page_index,
        y=y0,
        x=x0,
        x1=x1,
        y1=y1,
        size=size,
        text=text if kind == "code" else markdown.strip(),
        kind=kind,
        bullet=_has_bullet(bullets, x0, y0, y1) and not plain.strip().startswith("Contribution by"),
    )
    if kind == "body" and re.match(r"^\d+\.\s+\S", text):
        line.ordered = True
    return line


def _read_figures(document: pymupdf.Document, asset_dir: Path, relative_assets: str) -> list[Figure]:
    figures = []
    seen = set()
    index = 0
    for page_index, page in enumerate(document):
        for info in page.get_image_info(xrefs=True):
            if not info.get("xref"):
                continue
            if info.get("width", 0) < 150 or info.get("height", 0) < 80:
                continue
            bbox = pymupdf.Rect(info["bbox"]) & page.rect
            if bbox.width < 90 or bbox.height < 36:
                continue
            key = (info.get("digest"), page_index, round(bbox.y0))
            if key in seen:
                continue
            seen.add(key)
            index += 1
            figures.append(_save_clip(page, bbox, asset_dir, relative_assets, page_index, index, "figure"))
    return figures


def _replace_diagrams(document, extracted: Document, asset_dir: Path, relative_assets: str) -> None:
    pages = {line.page for line in extracted.lines if line.size < 8.3}
    drop = set()
    for page_index in pages:
        small = [line for line in extracted.lines if line.page == page_index and line.size < 8.3]
        if len(small) < 6:
            continue
        clip = pymupdf.Rect(
            min(line.x for line in small) - 24,
            min(line.y for line in small) - 16,
            max(line.x1 for line in small) + 24,
            max(line.y1 for line in small) + 16,
        ) & document[page_index].rect
        if clip.height < 40:
            continue
        extracted.figures.append(
            _save_clip(document[page_index], clip, asset_dir, relative_assets, page_index, page_index + 1, "diagram", dpi=130)
        )
        drop.add(page_index)
    if drop:
        extracted.lines = [line for line in extracted.lines if not (line.page in drop and line.size < 8.3)]


def _save_clip(page, clip, asset_dir: Path, relative_assets: str, page_index: int, index: int, prefix: str, dpi: int = 110) -> Figure:
    asset_dir.mkdir(parents=True, exist_ok=True)
    if prefix == "diagram":
        filename = f"{prefix}-{page_index + 1}.png"
    else:
        filename = f"{prefix}-{page_index + 1}-{index}.png"
    page.get_pixmap(clip=clip, dpi=dpi, alpha=False).save(asset_dir / filename)
    alt = "Flow diagram" if prefix == "diagram" else f"Figure from page {page_index + 1}"
    return Figure(page=page_index, y=clip.y0, path=f"{relative_assets}/{filename}", alt=alt)


def _merge_code_gutters(lines: list[Line]) -> list[Line]:
    merged: list[Line] = []
    for line in lines:
        if line.kind != "code":
            merged.append(line)
            continue
        if merged and _same_code_row(merged[-1], line):
            if len(line.text.strip()) > len(merged[-1].text.strip()):
                line.x1 = max(line.x1, merged[-1].x1)
                merged[-1] = line
            continue
        if not line.text.strip():
            continue
        if merged and merged[-1].kind == "code" and line.page == merged[-1].page and line.y - merged[-1].y > 22:
            merged.append(_blank_code_line(line))
        merged.append(line)
    return merged


def _demote_isolated_code(lines: list[Line]) -> None:
    for index, line in enumerate(lines):
        if line.kind != "code" or _stays_code(lines, index, line):
            continue
        stripped = line.text.strip()
        line.kind = "body"
        line.text = f"`{stripped}`" if stripped else line.text


def _stays_code(lines: list[Line], index: int, line: Line) -> bool:
    if _looks_like_code(line.text):
        return True
    if index == 0 or lines[index - 1].kind != "code":
        return False
    previous = lines[index - 1]
    same_page = previous.page == line.page and 0 <= line.y - previous.y < 30
    next_page = line.page == previous.page + 1 and line.y < 80
    return same_page or next_page


def _looks_like_code(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) >= 16 or any(char in stripped for char in "{}=[]()#<>" + BOX_DRAWING):
        return True
    return stripped.startswith(("-", "import ", "from ", "def ", "class ", "return ", "#"))


def _same_code_row(previous: Line, line: Line) -> bool:
    return previous.kind == "code" and line.page == previous.page and abs(line.y - previous.y) < 2.5


def _blank_code_line(line: Line) -> Line:
    return Line(page=line.page, y=line.y - 1, x=line.x, x1=line.x, y1=line.y, size=line.size, text="", kind="code")


def _classify(size: float, plain: str, ratio: float, spans: list) -> tuple[str, str]:
    code = _code_text(spans)
    stripped = plain.strip()
    if code is not None and (ratio >= 0.75 or (size <= 11.4 and ratio >= 0.5)):
        return "code", code
    if ratio < 0.5:
        for threshold, kind in HEADING_SIZES:
            if size >= threshold:
                return kind, stripped
    if 8.6 <= size < 11 and ratio < 0.4:
        return "caption", stripped
    return "body", stripped


def _code_text(spans: list) -> str | None:
    content = []
    saw_gutter = False
    for span in spans:
        text = span["text"]
        if "Menlo" not in span["font"] and text.strip():
            return None
        if text.strip().isdigit() and span["bbox"][0] < 92 and len(text.strip()) <= 4:
            saw_gutter = True
            continue
        content.append(text)
    if not content and saw_gutter:
        return ""
    if not content:
        return None
    return "".join(content).rstrip()


def _render_spans(spans: list, links: list) -> tuple[str, float]:
    groups = []
    menlo_chars = 0
    total_chars = 0
    for span in spans:
        text = span["text"] or ""
        total_chars += len(text)
        is_code = "Menlo" in span["font"]
        menlo_chars += len(text) if is_code else 0
        uri = _link_at(pymupdf.Rect(span["bbox"]), links)
        style = "code" if is_code else "text"
        if groups and groups[-1]["style"] == style and groups[-1]["uri"] == uri:
            groups[-1]["text"] += text
        else:
            groups.append({"style": style, "uri": uri, "text": text})
    parts = [_format_group(group) for group in groups]
    return "".join(parts), (menlo_chars / total_chars if total_chars else 0.0)


def _format_group(group: dict) -> str:
    piece = group["text"]
    if group["style"] == "code":
        match = re.match(r"^(\s*)(.*?)(\s*)$", piece, re.S)
        inner = match.group(2) if match else piece.strip()
        if inner and not re.fullmatch(r"\d+\.?", inner):
            fence = "``" if "`" in inner else "`"
            piece = f"{match.group(1)}{fence}{inner}{fence}{match.group(3)}"
    if group["uri"] and piece.strip():
        label = piece.strip()
        lead = piece[: len(piece) - len(piece.lstrip())]
        trail = piece[len(piece.rstrip()) :]
        piece = f"{lead}[{label}]({group['uri']}){trail}"
    return piece


def _link_at(bbox: pymupdf.Rect, links: list) -> str | None:
    center_x = (bbox.x0 + bbox.x1) / 2
    center_y = (bbox.y0 + bbox.y1) / 2
    for link in links:
        rect = link["from"]
        inside = rect.x0 - 1 <= center_x <= rect.x1 + 1 and rect.y0 - 1 <= center_y <= rect.y1 + 1
        if inside and link.get("uri"):
            return link["uri"]
    return None


def _is_footer(y: float, size: float, fonts: str, text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if size <= 8.4 and (y < 28 or y > 805):
        return True
    if "Times" in fonts and size <= 9:
        return True
    if re.fullmatch(r"\d+\s*/\s*\d+", stripped):
        return True
    if stripped.startswith("https://docs.is.sa/"):
        return True
    return bool(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2},?\s+\d{1,2}:\d{2}\s*[AP]M", stripped))


def _source_url(document: pymupdf.Document) -> str | None:
    for page in document:
        for link in page.get_links():
            uri = link.get("uri") or ""
            if uri.startswith("https://docs.is.sa/"):
                return uri
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                text = "".join(span["text"] for span in line["spans"]).strip()
                if text.startswith("https://docs.is.sa/"):
                    return text
    return None


def _bullet_marks(page) -> list[tuple[float, float]]:
    marks = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if 2.5 <= rect.width <= 14 and 2.5 <= rect.height <= 14 and rect.x0 < 150:
            marks.append((rect.x0, rect.y0))
    return marks


def _has_bullet(marks: list[tuple[float, float]], x: float, y: float, y1: float) -> bool:
    return any(bx < x and x - bx < 24 and (y - 3) <= by <= (y1 + 2) for bx, by in marks)
