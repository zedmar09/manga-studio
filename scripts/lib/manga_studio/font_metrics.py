from __future__ import annotations

import struct
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple


class FontMetricError(ValueError):
    pass


class SfntMetrics:
    """Read the horizontal metrics and Unicode cmap from a TrueType/OpenType font."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self.data = path.read_bytes()
            self.tables = self._table_directory()
            self.units_per_em = self._u16(self._table("head") + 18)
            if self.units_per_em <= 0:
                raise FontMetricError(f"font has invalid units-per-em: {path}")
            self.num_glyphs = self._u16(self._table("maxp") + 4)
            number_of_h_metrics = self._u16(self._table("hhea") + 34)
            if number_of_h_metrics <= 0 or number_of_h_metrics > self.num_glyphs:
                raise FontMetricError(f"font has invalid horizontal-metric count: {path}")
            hmtx = self._table("hmtx")
            self.advances = [self._u16(hmtx + index * 4) for index in range(number_of_h_metrics)]
            self.advances.extend([self.advances[-1]] * max(0, self.num_glyphs - len(self.advances)))
            self.cmap_offset, self.cmap_format = self._select_cmap()
        except (IndexError, struct.error, UnicodeDecodeError) as exc:
            raise FontMetricError(f"font structure is invalid or truncated: {path}") from exc

    def _u16(self, offset: int) -> int:
        return struct.unpack_from(">H", self.data, offset)[0]

    def _i16(self, offset: int) -> int:
        return struct.unpack_from(">h", self.data, offset)[0]

    def _u32(self, offset: int) -> int:
        return struct.unpack_from(">I", self.data, offset)[0]

    def _table_directory(self) -> Dict[str, Tuple[int, int]]:
        if len(self.data) < 12:
            raise FontMetricError(f"font is too short: {self.path}")
        num_tables = self._u16(4)
        tables: Dict[str, Tuple[int, int]] = {}
        for index in range(num_tables):
            record = 12 + index * 16
            tag = self.data[record:record + 4].decode("ascii", errors="replace")
            offset = self._u32(record + 8)
            length = self._u32(record + 12)
            if offset + length > len(self.data):
                raise FontMetricError(f"font table {tag!r} leaves the file: {self.path}")
            tables[tag] = (offset, length)
        return tables

    def _table(self, name: str) -> int:
        if name not in self.tables:
            raise FontMetricError(f"font is missing required {name!r} table: {self.path}")
        return self.tables[name][0]

    def _select_cmap(self) -> Tuple[int, int]:
        cmap = self._table("cmap")
        candidates: List[Tuple[int, int, int]] = []
        for index in range(self._u16(cmap + 2)):
            record = cmap + 4 + index * 8
            platform = self._u16(record)
            encoding = self._u16(record + 2)
            offset = cmap + self._u32(record + 4)
            fmt = self._u16(offset)
            if fmt in {4, 12}:
                priority = 3 if fmt == 12 and platform in {0, 3} else 2 if platform in {0, 3} else 1
                if platform == 3 and encoding == 10:
                    priority += 2
                candidates.append((priority, offset, fmt))
        if not candidates:
            raise FontMetricError(f"font has no supported Unicode cmap: {self.path}")
        _, offset, fmt = max(candidates)
        return offset, fmt

    def glyph_id(self, codepoint: int) -> int:
        if self.cmap_format == 12:
            groups = self._u32(self.cmap_offset + 12)
            start = self.cmap_offset + 16
            low, high = 0, groups - 1
            while low <= high:
                middle = (low + high) // 2
                offset = start + middle * 12
                first = self._u32(offset)
                last = self._u32(offset + 4)
                if codepoint < first:
                    high = middle - 1
                elif codepoint > last:
                    low = middle + 1
                else:
                    return self._u32(offset + 8) + codepoint - first
            return 0

        seg_count = self._u16(self.cmap_offset + 6) // 2
        end_codes = self.cmap_offset + 14
        start_codes = end_codes + seg_count * 2 + 2
        deltas = start_codes + seg_count * 2
        ranges = deltas + seg_count * 2
        for index in range(seg_count):
            end = self._u16(end_codes + index * 2)
            if codepoint > end:
                continue
            start = self._u16(start_codes + index * 2)
            if codepoint < start:
                return 0
            delta = self._i16(deltas + index * 2)
            range_offset_address = ranges + index * 2
            range_offset = self._u16(range_offset_address)
            if range_offset == 0:
                return (codepoint + delta) & 0xFFFF
            glyph_address = range_offset_address + range_offset + (codepoint - start) * 2
            if glyph_address + 2 > len(self.data):
                return 0
            glyph = self._u16(glyph_address)
            return (glyph + delta) & 0xFFFF if glyph else 0
        return 0

    def text_width(self, text: str, font_size: float) -> float:
        units = 0
        for character in text:
            glyph = self.glyph_id(ord(character))
            units += self.advances[glyph] if glyph < len(self.advances) else self.advances[0]
        return units * font_size / self.units_per_em


def is_cjk(character: str) -> bool:
    if not character:
        return False
    codepoint = ord(character)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x9FFF
        or 0xAC00 <= codepoint <= 0xD7AF
        or unicodedata.east_asian_width(character) in {"W", "F"}
    )


def estimated_text_width(text: str, font_size: float) -> float:
    width = 0.0
    for character in text:
        if character.isspace():
            width += 0.3
        elif is_cjk(character):
            width += 1.0
        elif unicodedata.category(character).startswith("P"):
            width += 0.42
        else:
            width += 0.56
    return width * font_size
