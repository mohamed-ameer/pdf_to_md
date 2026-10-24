"""Group extracted lines into headings, paragraphs, lists, code, and tables."""

import re

from converter.extract import Line


def build_blocks(lines: list[Line]) -> list[dict]:
    return _BlockBuilder(lines).build()


class _BlockBuilder:
    def __init__(self, lines: list[Line]):
        self.bands = _bands(lines)
        self.blocks: list[dict] = []
        self.table_rows: list[list[str]] | None = None
        self.columns: list[float] | None = None
        self.table_page = -1
        self.table_y = 0.0
        self.origin_page = -1
        self.origin_y = 0.0

    def build(self) -> list[dict]:
        for band in self.bands:
            line = band[0]
            if _is_table_band(band):
                self._add_table_band(band, line)
                continue
            if self._absorb_table_continuation(band, line):
                continue
            self._close_table()
            self._add_content(band, line)
        self._close_table()
        return self.blocks

    def _add_table_band(self, band: list[Line], line: Line) -> None:
        if self.table_rows is None:
            self._start_table(band, line)
            return
        row = self._row_from_band(band)
        same_table = line.page == self.table_page or (line.page == self.table_page + 1 and line.y < 180)
        if same_table and row and not row[0].strip():
            self._append_to_last_row(row, line)
            return
        if same_table:
            self.table_rows.append(row)
            self.table_page = line.page
            self.table_y = line.y
            return
        self._close_table()
        self._start_table(band, line)

    def _absorb_table_continuation(self, band: list[Line], line: Line) -> bool:
        if self.table_rows is None or line.kind not in {"body", "caption"} or len(band) != 1:
            return False
        gap = line.y - self.table_y
        same_page = line.page == self.table_page and 0 < gap < 26
        next_page = line.page == self.table_page + 1 and line.y < 80
        column = _nearest_column(line.x, self.columns or [])
        if not (same_page or next_page) or column is None or line.bullet or line.ordered:
            return False
        while len(self.table_rows[-1]) <= column:
            self.table_rows[-1].append("")
        self.table_rows[-1][column] = _join_text(self.table_rows[-1][column], line.text.strip(), line.x1)
        self.table_page = line.page
        self.table_y = line.y
        return True

    def _add_content(self, band: list[Line], line: Line) -> None:
        if line.kind == "code":
            self._add_code(line)
            return
        if line.kind in {"h1", "h2", "h3", "h4"}:
            self._add_heading(line)
            return
        if line.bullet or line.ordered or line.text.startswith(("✅", "❌")):
            self._add_item(line)
            return
        relation = _relation(self.blocks[-1], line) if self.blocks else None
        if relation == "continue":
            self._extend_last(line)
            return
        if relation == "sibling":
            self._add_item(line, level=self.blocks[-1]["level"], ordered=False)
            return
        block_type = "caption" if line.kind == "caption" else "paragraph"
        self.blocks.append(_text_block(block_type, line))

    def _add_code(self, line: Line) -> None:
        if self.blocks and self.blocks[-1]["type"] == "code" and _code_continues(self.blocks[-1], line):
            previous = self.blocks[-1]["lines"][-1] if self.blocks[-1]["lines"] else ""
            if self.blocks[-1]["lines"] and _should_join_code(previous, self.blocks[-1]["x1"], line.text):
                glue = "" if previous.rstrip().endswith(("-", "/", "\\", "(", "{")) else " "
                self.blocks[-1]["lines"][-1] = previous.rstrip() + glue + line.text.lstrip()
            else:
                self.blocks[-1]["lines"].append(line.text)
            self.blocks[-1]["x1"] = line.x1
            self.blocks[-1]["end_page"] = line.page
            return
        self.blocks.append(
            {
                "type": "code",
                "lines": [line.text],
                "x1": line.x1,
                "page": line.page,
                "end_page": line.page,
                "y": line.y,
            }
        )

    def _add_heading(self, line: Line) -> None:
        previous = self.blocks[-1] if self.blocks else None
        can_join = (
            previous
            and previous["type"] == "heading"
            and previous["level"] == line.kind
            and line.page == previous["page"]
            and line.y - previous["y"] < 40
            and not re.match(r"^\d+\.\s", line.text)
        )
        if can_join:
            previous["text"] = _join_text(previous["text"], line.text, previous["x1"])
            previous["y"] = line.y
            previous["x1"] = line.x1
            return
        self.blocks.append(
            {
                "type": "heading",
                "level": line.kind,
                "text": line.text,
                "page": line.page,
                "y": line.y,
                "x1": line.x1,
            }
        )

    def _add_item(self, line: Line, level: int | None = None, ordered: bool | None = None) -> None:
        self.blocks.append(
            {
                "type": "item",
                "text": line.text,
                "level": level if level is not None else max(1, round((line.x - 58) / 16.5)),
                "ordered": line.ordered if ordered is None else ordered,
                "page": line.page,
                "y": line.y,
                "x": line.x,
                "x1": line.x1,
            }
        )

    def _extend_last(self, line: Line) -> None:
        block = self.blocks[-1]
        block["text"] = _join_text(block["text"], line.text, block.get("x1", 0))
        block["page"] = line.page
        block["y"] = line.y
        block["x1"] = line.x1

    def _start_table(self, band: list[Line], line: Line) -> None:
        self.columns = [item.x for item in band]
        self.table_rows = [[item.text.strip() for item in band]]
        self.table_page = line.page
        self.table_y = line.y
        self.origin_page = line.page
        self.origin_y = line.y

    def _row_from_band(self, band: list[Line]) -> list[str]:
        row = [""] * len(self.columns or [])
        for item in band:
            index = _column_index(item.x, self.columns)
            while len(row) <= index:
                row.append("")
            row[index] = _join_text(row[index], item.text.strip(), 0) if row[index] else item.text.strip()
        return row

    def _append_to_last_row(self, row: list[str], line: Line) -> None:
        for index, cell in enumerate(row):
            if not cell.strip():
                continue
            while len(self.table_rows[-1]) <= index:
                self.table_rows[-1].append("")
            self.table_rows[-1][index] = _join_text(self.table_rows[-1][index], cell, 0)
        self.table_page = line.page
        self.table_y = line.y

    def _close_table(self) -> None:
        if not self.table_rows:
            self.table_rows = None
            self.columns = None
            return
        width = max(len(row) for row in self.table_rows)
        rows = [row + [""] * (width - len(row)) for row in self.table_rows]
        rows = [row for row in rows if any(cell.strip() for cell in row)]
        if len(rows) >= 2 and width >= 2:
            self.blocks.append({"type": "table", "rows": rows, "page": self.origin_page, "y": self.origin_y})
        else:
            for row in rows:
                text = " ".join(cell for cell in row if cell.strip())
                if text:
                    self.blocks.append(
                        {"type": "paragraph", "text": text, "page": self.origin_page, "y": self.origin_y, "x": 60.0, "x1": 0}
                    )
        self.table_rows = None
        self.columns = None


def _bands(lines: list[Line]) -> list[list[Line]]:
    bands: list[list[Line]] = []
    for line in lines:
        structural = line.kind in {"h1", "h2", "h3", "h4", "code"}
        if bands and not structural and bands[-1][0].kind not in {"h1", "h2", "h3", "h4", "code"}:
            previous = bands[-1][-1]
            if line.page == previous.page and abs(line.y - previous.y) < 3.2:
                bands[-1].append(line)
                continue
        bands.append([line])
    for band in bands:
        band.sort(key=lambda item: item.x)
    return bands


def _is_table_band(band: list[Line]) -> bool:
    if len(band) < 2 or any(item.kind in {"h1", "h2", "h3", "h4", "code"} for item in band):
        return False
    gaps = [band[index + 1].x - band[index].x1 for index in range(len(band) - 1)]
    return max(gaps) > 28


def _relation(block: dict, line: Line) -> str | None:
    if block["type"] not in {"paragraph", "item", "caption"}:
        return None
    if line.bullet or line.ordered or line.kind in {"h1", "h2", "h3", "h4", "code"}:
        return None
    if "page" not in block or "y" not in block:
        return None
    same_column = abs(line.x - block.get("x", line.x)) <= 10
    wrapped_deeper = block.get("x", line.x) + 8 < line.x < block.get("x", line.x) + 36
    if line.page == block["page"]:
        gap = line.y - block["y"]
    elif line.page == block["page"] + 1 and line.y < 90 and (block.get("x1", 0) > 470 or block["text"].rstrip().endswith("-")):
        gap = 12
        same_column = True
        wrapped_deeper = False
    else:
        return None
    if gap <= 0 or gap > 24 or not (same_column or wrapped_deeper):
        return None
    previous = block["text"].rstrip()
    if block.get("x1", 0) > 470 or previous.endswith("-") or wrapped_deeper:
        return "continue"
    if block["type"] == "item" and same_column and line.text[:1].isupper():
        return "sibling"
    if same_column and gap < 20:
        return "continue"
    return None


def _code_continues(block: dict, line: Line) -> bool:
    end_page = block.get("end_page", block["page"])
    if line.page == end_page:
        return True
    return line.page == end_page + 1 and line.y < 120


def _should_join_code(previous: str, previous_x1: float, nxt: str) -> bool:
    if previous_x1 < 440:
        return False
    if previous.rstrip("\n").endswith(("-", " ", "/", "\\", ",", "(", "{")) or previous_x1 > 490:
        return True
    token = nxt.strip()
    return previous_x1 > 450 and " " not in token and len(token) < 40


def _join_text(previous: str, nxt: str, previous_x1: float) -> str:
    previous = previous.rstrip()
    nxt = nxt.lstrip()
    if not previous:
        return nxt
    if previous.endswith("-") and nxt and (nxt[0].islower() or nxt[0] in "/{.#_"):
        return previous + nxt
    if previous_x1 > 450 and previous.endswith("-"):
        return previous + nxt
    return previous + " " + nxt


def _nearest_column(x: float, columns: list[float]) -> int | None:
    if not columns:
        return None
    best = min(range(len(columns)), key=lambda index: abs(columns[index] - x))
    if abs(columns[best] - x) > 28:
        return None
    return best


def _column_index(x: float, columns: list[float]) -> int:
    nearest = _nearest_column(x, columns)
    if nearest is not None:
        return nearest
    columns.append(x)
    return len(columns) - 1


def _text_block(block_type: str, line: Line) -> dict:
    return {
        "type": block_type,
        "text": line.text,
        "page": line.page,
        "y": line.y,
        "x": line.x,
        "x1": line.x1,
    }
