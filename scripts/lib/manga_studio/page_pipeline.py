from __future__ import annotations

import base64
import html
import math
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .font_metrics import FontMetricError, SfntMetrics, estimated_text_width, is_cjk


Point = Tuple[float, float]


LETTERING_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "speech": {"shape": "ellipse", "font_size": 34, "font_weight": 700},
    "caption": {"shape": "rectangle", "font_size": 30, "font_weight": 700},
    "thought": {"shape": "cloud", "font_size": 32, "font_weight": 600},
    "sfx": {"shape": "none", "font_size": 54, "font_weight": 900},
    "whisper": {"shape": "ellipse", "font_size": 28, "font_weight": 400},
    "shout": {"shape": "burst", "font_size": 36, "font_weight": 900},
    "radio": {"shape": "jagged", "font_size": 30, "font_weight": 700},
    "narration": {"shape": "rectangle", "font_size": 30, "font_weight": 700},
}


def box_polygon(box: Dict[str, Any]) -> List[Point]:
    x = float(box["x"])
    y = float(box["y"])
    width = float(box["width"])
    height = float(box["height"])
    return [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]


def panel_polygon(panel: Dict[str, Any]) -> List[Point]:
    polygon = panel.get("clip_polygon")
    if isinstance(polygon, list) and polygon:
        return [(float(point["x"]), float(point["y"])) for point in polygon]
    return box_polygon(panel["frame"])


def source_box_to_page(panel: Dict[str, Any], box: Dict[str, Any]) -> Dict[str, float]:
    """Project a normalized source-image box through the compositor's fit/focus transform."""
    frame = panel["frame"]
    source = panel["source_canvas"]
    source_width = float(source["width"])
    source_height = float(source["height"])
    frame_width = float(frame["width"])
    frame_height = float(frame["height"])
    if panel.get("fit") == "contain":
        scale = min(frame_width / source_width, frame_height / source_height)
    else:
        scale = max(frame_width / source_width, frame_height / source_height)
    rendered_width = source_width * scale
    rendered_height = source_height * scale
    focus = panel.get("focus", {}) if isinstance(panel.get("focus"), dict) else {}
    focus_x = float(focus.get("x", 0.5))
    focus_y = float(focus.get("y", 0.5))
    offset_x = 0.0 if focus_x < 0.34 else frame_width - rendered_width if focus_x > 0.66 else (frame_width - rendered_width) / 2
    offset_y = 0.0 if focus_y < 0.34 else frame_height - rendered_height if focus_y > 0.66 else (frame_height - rendered_height) / 2
    return {
        "x": float(frame["x"]) + offset_x + float(box["x"]) * rendered_width,
        "y": float(frame["y"]) + offset_y + float(box["y"]) * rendered_height,
        "width": float(box["width"]) * rendered_width,
        "height": float(box["height"]) * rendered_height,
    }


def polygon_area(points: Sequence[Point]) -> float:
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_segment_intersection(a: Point, b: Point, c: Point, d: Point) -> bool:
    first = _orientation(a, b, c)
    second = _orientation(a, b, d)
    third = _orientation(c, d, a)
    fourth = _orientation(c, d, b)
    return (first > 0 > second or second > 0 > first) and (third > 0 > fourth or fourth > 0 > third)


def polygon_self_intersects(points: Sequence[Point]) -> bool:
    count = len(points)
    for first in range(count):
        a = points[first]
        b = points[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count} or (second + 1) % count == first:
                continue
            c = points[second]
            d = points[(second + 1) % count]
            if _proper_segment_intersection(a, b, c, d):
                return True
    return False


def point_in_polygon(point: Point, polygon: Sequence[Point], include_boundary: bool = True) -> bool:
    x, y = point
    inside = False
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        cross = _orientation(first, second, point)
        if abs(cross) < 1e-9:
            if min(first[0], second[0]) <= x <= max(first[0], second[0]) and min(first[1], second[1]) <= y <= max(first[1], second[1]):
                return include_boundary
        if (first[1] > y) != (second[1] > y):
            crossing_x = (second[0] - first[0]) * (y - first[1]) / (second[1] - first[1]) + first[0]
            if x < crossing_x:
                inside = not inside
    return inside


def polygon_contains_box(polygon: Sequence[Point], box: Dict[str, Any]) -> bool:
    return all(point_in_polygon(point, polygon) for point in box_polygon(box))


def boxes_overlap(first: Dict[str, Any], second: Dict[str, Any]) -> bool:
    return (
        first["x"] < second["x"] + second["width"]
        and second["x"] < first["x"] + first["width"]
        and first["y"] < second["y"] + second["height"]
        and second["y"] < first["y"] + first["height"]
    )


def polygons_overlap(first: Sequence[Point], second: Sequence[Point]) -> bool:
    if len(first) == len(second) and set(first) == set(second):
        return True
    for index, a in enumerate(first):
        b = first[(index + 1) % len(first)]
        for other_index, c in enumerate(second):
            d = second[(other_index + 1) % len(second)]
            if _proper_segment_intersection(a, b, c, d):
                return True
    if any(point_in_polygon(point, second, include_boundary=False) for point in first):
        return True
    if any(point_in_polygon(point, first, include_boundary=False) for point in second):
        return True
    first_center = (
        sum(point[0] for point in first) / len(first),
        sum(point[1] for point in first) / len(first),
    )
    second_center = (
        sum(point[0] for point in second) / len(second),
        sum(point[1] for point in second) / len(second),
    )
    return point_in_polygon(first_center, second, include_boundary=False) or point_in_polygon(
        second_center, first, include_boundary=False
    )


def polygon_svg_points(points: Sequence[Point]) -> str:
    return " ".join(f"{_number(x)},{_number(y)}" for x, y in points)


def _number(value: float) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.3f}".rstrip("0").rstrip(".")


def next_version_path(directory: Path, stem: str, suffix: str) -> Path:
    versions: List[int] = []
    pattern = re.compile(rf"^{re.escape(stem)}-v([0-9]{{3}}){re.escape(suffix)}$")
    if directory.is_dir():
        for path in directory.iterdir():
            match = pattern.match(path.name)
            if match:
                versions.append(int(match.group(1)))
    return directory / f"{stem}-v{max(versions, default=0) + 1:03d}{suffix}"


def latest_version_path(directory: Path, stem: str, suffix: str) -> Path | None:
    candidates: List[Tuple[int, Path]] = []
    pattern = re.compile(rf"^{re.escape(stem)}-v([0-9]{{3}}){re.escape(suffix)}$")
    if directory.is_dir():
        for path in directory.iterdir():
            match = pattern.match(path.name)
            if match:
                candidates.append((int(match.group(1)), path))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _style_value(item: Dict[str, Any], page_style: Dict[str, Any], key: str, fallback: Any) -> Any:
    return item.get(key, page_style.get(key, fallback))


def wrap_text(text: str, max_chars: int) -> List[str]:
    wrapped: List[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        current: List[str] = []
        for word in words:
            while len(word) > max_chars:
                if current:
                    wrapped.append(" ".join(current))
                    current = []
                wrapped.append(word[:max_chars])
                word = word[max_chars:]
            candidate = " ".join([*current, word])
            if current and len(candidate) > max_chars:
                wrapped.append(" ".join(current))
                current = [word]
            elif word:
                current.append(word)
        wrapped.append(" ".join(current))
    return wrapped or [""]


DEFAULT_KINSOKU_OPENING = "([{〈《「『【〔（［｛‘“"
DEFAULT_KINSOKU_CLOSING = ")]},.!?:;、。〉》」』】〕）］｝’”！？，．"


def _measure_text(text: str, font_size: int, metrics: SfntMetrics | None) -> float:
    return metrics.text_width(text, font_size) if metrics else estimated_text_width(text, font_size)


def _cjk_lines(
    text: str,
    max_width: float,
    font_size: int,
    metrics: SfntMetrics | None,
    opening: str,
    closing: str,
) -> List[str]:
    lines: List[str] = []
    current = ""
    for character in text:
        if character == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + character
        if current and _measure_text(candidate, font_size, metrics) > max_width:
            if character in closing:
                current += character
                continue
            if current[-1] in opening and len(current) > 1:
                carry = current[-1]
                lines.append(current[:-1])
                current = carry + character
            else:
                lines.append(current)
                current = character
        else:
            current = candidate
    if current or not lines:
        lines.append(current)
    return lines


def _latin_lines(text: str, max_width: float, font_size: int, metrics: SfntMetrics | None) -> List[str]:
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if current and _measure_text(candidate, font_size, metrics) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
            while current and _measure_text(current, font_size, metrics) > max_width and len(current) > 1:
                split_at = max(1, len(current) - 1)
                while split_at > 1 and _measure_text(current[:split_at], font_size, metrics) > max_width:
                    split_at -= 1
                lines.append(current[:split_at])
                current = current[split_at:]
        lines.append(current)
    return lines or [""]


def wrap_text_to_width(
    text: str,
    max_width: float,
    font_size: int,
    *,
    metrics: SfntMetrics | None = None,
    profile: str = "latin",
    opening: str = DEFAULT_KINSOKU_OPENING,
    closing: str = DEFAULT_KINSOKU_CLOSING,
) -> List[str]:
    use_cjk = profile in {"cjk", "japanese"} or (profile == "custom" and any(is_cjk(char) for char in text))
    if use_cjk:
        return _cjk_lines(text, max_width, font_size, metrics, opening, closing)
    return _latin_lines(text, max_width, font_size, metrics)


def fit_lettering_text(
    item: Dict[str, Any],
    page_style: Dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> Dict[str, Any]:
    page_style = page_style or {}
    kind_defaults = LETTERING_DEFAULTS.get(item.get("kind", "speech"), LETTERING_DEFAULTS["speech"])
    box = item["box"]
    padding = int(_style_value(item, page_style, "padding", 20))
    requested_size = int(_style_value(item, page_style, "font_size", kind_defaults["font_size"]))
    minimum_size = int(_style_value(item, page_style, "min_font_size", 14))
    line_ratio = float(_style_value(item, page_style, "line_height", 1.18))
    usable_width = max(1, box["width"] - padding * 2)
    usable_height = max(1, box["height"] - padding * 2)
    writing_mode = item.get("writing_mode", "horizontal")
    profile = str(_style_value(item, page_style, "line_break_profile", "latin"))
    opening = str(page_style.get("kinsoku_opening_characters", DEFAULT_KINSOKU_OPENING))
    closing = str(page_style.get("kinsoku_closing_characters", DEFAULT_KINSOKU_CLOSING))
    metrics = None
    font_file = page_style.get("font_file")
    if project_root is not None and isinstance(font_file, str):
        try:
            metrics = SfntMetrics(project_root / font_file)
        except (OSError, FontMetricError):
            metrics = None
    ruby_size = max(8, int(requested_size * 0.45)) if item.get("ruby_text") else 0

    for font_size in range(requested_size, minimum_size - 1, -1):
        if writing_mode == "vertical":
            glyph_count = len("".join(item["text"].split()))
            fits = glyph_count * font_size <= usable_height and font_size + ruby_size <= usable_width
            return {
                "font_size": font_size,
                "line_height": max(1, int(font_size * line_ratio)),
                "lines": [item["text"]],
                "fits": fits,
                "padding": padding,
            }
        lines = wrap_text_to_width(
            item["text"], usable_width, font_size, metrics=metrics, profile=profile, opening=opening, closing=closing
        )
        line_height = max(1, int(font_size * line_ratio))
        if len(lines) * line_height + ruby_size <= usable_height:
            return {
                "font_size": font_size,
                "line_height": line_height,
                "lines": lines,
                "fits": True,
                "padding": padding,
            }
    return {
        "font_size": minimum_size,
        "line_height": max(1, int(minimum_size * line_ratio)),
        "lines": wrap_text_to_width(
            item["text"], usable_width, minimum_size, metrics=metrics, profile=profile, opening=opening, closing=closing
        ),
        "fits": False,
        "padding": padding,
    }


def _radial_points(box: Dict[str, Any], count: int, inner_ratio: float) -> List[Point]:
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
    radius_x = box["width"] / 2
    radius_y = box["height"] / 2
    points: List[Point] = []
    for index in range(count * 2):
        angle = -math.pi / 2 + math.pi * index / count
        ratio = 1 if index % 2 == 0 else inner_ratio
        points.append((center_x + math.cos(angle) * radius_x * ratio, center_y + math.sin(angle) * radius_y * ratio))
    return points


def _cloud_path(box: Dict[str, Any]) -> str:
    points = _radial_points(box, 10, 0.88)
    commands = [f"M {_number(points[0][0])} {_number(points[0][1])}"]
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        midpoint = ((point[0] + following[0]) / 2, (point[1] + following[1]) / 2)
        commands.append(
            f"Q {_number(point[0])} {_number(point[1])} {_number(midpoint[0])} {_number(midpoint[1])}"
        )
    commands.append("Z")
    return " ".join(commands)


def _shape_svg(shape: str, box: Dict[str, Any], fill: str, stroke: str, stroke_width: int, opacity: float) -> str:
    common = (
        f'fill="{html.escape(fill)}" stroke="{html.escape(stroke)}" '
        f'stroke-width="{stroke_width}" opacity="{opacity}"'
    )
    if shape == "none":
        return ""
    if shape == "ellipse":
        return (
            f'<ellipse cx="{box["x"] + box["width"] / 2}" cy="{box["y"] + box["height"] / 2}" '
            f'rx="{box["width"] / 2}" ry="{box["height"] / 2}" {common}/>'
        )
    if shape == "rounded":
        radius = min(28, box["width"] // 5, box["height"] // 5)
        return (
            f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["width"]}" height="{box["height"]}" '
            f'rx="{radius}" ry="{radius}" {common}/>'
        )
    if shape == "rectangle":
        return (
            f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["width"]}" height="{box["height"]}" {common}/>'
        )
    if shape == "cloud":
        return f'<path d="{_cloud_path(box)}" stroke-linejoin="round" {common}/>'
    inner = 0.74 if shape == "burst" else 0.9
    points = _radial_points(box, 12 if shape == "burst" else 18, inner)
    return f'<polygon points="{polygon_svg_points(points)}" stroke-linejoin="round" {common}/>'


def _tail_svg(item: Dict[str, Any], shape: str, fill: str, stroke: str, stroke_width: int) -> str:
    tail = item.get("tail_to")
    if not isinstance(tail, dict) or shape == "none":
        return ""
    box = item["box"]
    anchor_x = box["x"] + box["width"] / 2
    anchor_y = box["y"] + box["height"]
    if shape == "cloud":
        first_x = anchor_x + (tail["x"] - anchor_x) * 0.38
        first_y = anchor_y + (tail["y"] - anchor_y) * 0.38
        second_x = anchor_x + (tail["x"] - anchor_x) * 0.72
        second_y = anchor_y + (tail["y"] - anchor_y) * 0.72
        return (
            f'<circle cx="{_number(first_x)}" cy="{_number(first_y)}" r="12" fill="{html.escape(fill)}" '
            f'stroke="{html.escape(stroke)}" stroke-width="{stroke_width}"/>'
            f'<circle cx="{_number(second_x)}" cy="{_number(second_y)}" r="7" fill="{html.escape(fill)}" '
            f'stroke="{html.escape(stroke)}" stroke-width="{stroke_width}"/>'
        )
    return (
        f'<path d="M {_number(anchor_x - 18)} {_number(anchor_y - 2)} L {tail["x"]} {tail["y"]} '
        f'L {_number(anchor_x + 18)} {_number(anchor_y - 2)} Z" fill="{html.escape(fill)}" '
        f'stroke="{html.escape(stroke)}" stroke-width="{stroke_width}" stroke-linejoin="round"/>'
    )


def _embedded_font_style(page_style: Dict[str, Any], project_root: Path | None) -> str:
    font_file = page_style.get("font_file")
    if not page_style.get("embed_font") or project_root is None or not isinstance(font_file, str):
        return ""
    path = project_root / font_file
    if not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "font/ttf"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    family = html.escape(str(page_style.get("font_family", "Manga Studio Embedded")), quote=True)
    return f'<style>@font-face{{font-family:"{family}";src:url(data:{mime};base64,{payload})}}</style>'


def lettering_svg(page: Dict[str, Any], project_root: Path | None = None) -> str:
    snippets: List[str] = ['<g id="lettering">']
    page_style = page.get("lettering_style", {})
    embedded = _embedded_font_style(page_style, project_root)
    if embedded:
        snippets.append(embedded)
    for index, item in enumerate(page.get("lettering", [])):
        box = item["box"]
        kind = item.get("kind", "speech")
        defaults = LETTERING_DEFAULTS.get(kind, LETTERING_DEFAULTS["speech"])
        shape = item.get("shape", defaults["shape"])
        layout = fit_lettering_text(item, page_style, project_root)
        font_family = html.escape(str(_style_value(item, page_style, "font_family", "Noto Sans, Arial, sans-serif")))
        font_weight = int(_style_value(item, page_style, "font_weight", defaults["font_weight"]))
        font_style = item.get("font_style", "normal")
        fill = str(_style_value(item, page_style, "fill", "#fff"))
        stroke = str(_style_value(item, page_style, "stroke", "#000"))
        stroke_width = int(_style_value(item, page_style, "stroke_width", 4))
        text_color = str(_style_value(item, page_style, "text_color", "#000"))
        opacity = float(item.get("opacity", 1))
        rotation = int(item.get("rotation", 0))
        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2
        transform = f' transform="rotate({rotation} {_number(center_x)} {_number(center_y)})"' if rotation else ""
        element_id = html.escape(item.get("lettering_id", f"letter-{index + 1}-{item['panel_id']}"))

        snippets.append(f'<g id="{element_id}" data-kind="{html.escape(kind)}"{transform}>')
        tail = _tail_svg(item, shape, fill, stroke, stroke_width)
        if tail:
            snippets.append(tail)
        balloon = _shape_svg(shape, box, fill, stroke, stroke_width, opacity)
        if balloon:
            snippets.append(balloon)

        font_size = layout["font_size"]
        if item.get("writing_mode", "horizontal") == "vertical":
            snippets.append(
                f'<text x="{_number(center_x)}" y="{box["y"] + layout["padding"]}" '
                f'font-family="{font_family}" font-size="{font_size}" font-weight="{font_weight}" '
                f'font-style="{font_style}" fill="{html.escape(text_color)}" text-anchor="middle" '
                f'writing-mode="vertical-rl">{html.escape(item["text"])}</text>'
            )
        else:
            text_height = layout["line_height"] * len(layout["lines"])
            ruby_text = item.get("ruby_text")
            ruby_size = max(8, int(font_size * 0.45)) if ruby_text else 0
            start_y = box["y"] + (box["height"] - text_height - ruby_size) / 2 + font_size + ruby_size
            text_x = center_x
            text_stroke = ""
            if kind == "sfx":
                text_stroke = (
                    f' stroke="{html.escape(stroke)}" stroke-width="{max(1, stroke_width)}" '
                    'paint-order="stroke fill" stroke-linejoin="round"'
                )
            if ruby_text:
                snippets.append(
                    f'<text x="{_number(text_x)}" y="{_number(start_y - font_size)}" text-anchor="middle" '
                    f'font-family="{font_family}" font-size="{ruby_size}" font-weight="{font_weight}" '
                    f'fill="{html.escape(text_color)}">{html.escape(str(ruby_text))}</text>'
                )
            snippets.append(
                f'<text x="{_number(text_x)}" y="{_number(start_y)}" text-anchor="middle" '
                f'font-family="{font_family}" font-size="{font_size}" font-weight="{font_weight}" '
                f'font-style="{font_style}" fill="{html.escape(text_color)}"{text_stroke}>'
            )
            for line_index, line in enumerate(layout["lines"]):
                dy = 0 if line_index == 0 else layout["line_height"]
                snippets.append(f'<tspan x="{_number(text_x)}" dy="{dy}">{html.escape(line)}</tspan>')
            snippets.append("</text>")
        snippets.append("</g>")
    snippets.append("</g>")
    return "\n".join(snippets)


def _finding(
    code: str,
    severity: str,
    message: str,
    *,
    panel_ids: Iterable[str] = (),
    lettering_ids: Iterable[str] = (),
) -> Dict[str, Any]:
    finding: Dict[str, Any] = {"severity": severity, "message": message, "code": code}
    panels = [item for item in panel_ids if isinstance(item, str)]
    letters = [item for item in lettering_ids if isinstance(item, str)]
    if panels:
        finding["panel_ids"] = panels
    if letters:
        finding["lettering_ids"] = letters
    return finding


def page_quality_review(
    page: Dict[str, Any],
    *,
    project_id: str,
    target: str,
    review_id: str,
    validation_errors: Sequence[str] = (),
    project_root: Path | None = None,
) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    scores = {
        "readability": 100,
        "reading_flow": 100,
        "pacing": 100,
        "visual_variety": 100,
        "continuity": 100,
        "lettering": 100,
        "page_impact": 100,
    }

    for message in validation_errors:
        findings.append(_finding("PAGE_VALIDATION", "error", message))
        scores["readability"] -= 12
        scores["lettering"] -= 12

    panels = page.get("panels", [])
    panel_ids = [panel.get("panel_id") for panel in panels if isinstance(panel, dict)]
    if not page.get("reading_sequence"):
        findings.append(_finding(
            "READING_SEQUENCE_MISSING",
            "warning",
            "Define reading_sequence explicitly so irregular layouts remain unambiguous.",
        ))
        scores["reading_flow"] -= 20

    intent = page.get("page_intent")
    if not isinstance(intent, dict):
        findings.append(_finding(
            "PAGE_INTENT_MISSING",
            "warning",
            "Add page_intent so panel scale, pacing, and page-turn impact can be reviewed against purpose.",
        ))
        scores["pacing"] -= 25
        scores["page_impact"] -= 25
    else:
        curve = intent.get("emotional_curve", [])
        if curve and len(curve) != len(panels):
            findings.append(_finding(
                "EMOTIONAL_CURVE_LENGTH",
                "warning",
                "page_intent.emotional_curve should contain one intensity value per panel.",
            ))
            scores["pacing"] -= 15
        if intent.get("page_turn", {}).get("kind") == "none" and intent.get("pacing") == "impact":
            findings.append(_finding(
                "IMPACT_WITHOUT_TURN",
                "warning",
                "An impact-paced page should state the intended turn, reveal, decision, or emotional payoff.",
            ))
            scores["page_impact"] -= 15

    events = [panel.get("event") for panel in panels if isinstance(panel, dict)]
    described_events = [event for event in events if isinstance(event, dict)]
    if len(described_events) != len(panels):
        findings.append(_finding(
            "EVENT_DIRECTION_INCOMPLETE",
            "warning",
            "Every panel should define one dominant event, shot, camera angle, intensity, and action direction.",
            panel_ids=[panel_id for panel_id, event in zip(panel_ids, events) if not isinstance(event, dict)],
        ))
        scores["pacing"] -= 20
        scores["visual_variety"] -= 25
        scores["continuity"] -= 10
    if described_events:
        shot_sizes = {event.get("shot_size") for event in described_events}
        angles = {event.get("camera_angle") for event in described_events}
        desired_shots = min(3, len(described_events))
        if len(shot_sizes) < desired_shots:
            findings.append(_finding(
                "SHOT_VARIETY_LOW",
                "warning",
                "Vary shot size according to event importance; repeated framing can flatten the manga rhythm.",
            ))
            scores["visual_variety"] -= 20
        if len(described_events) >= 3 and len(angles) < 2:
            findings.append(_finding(
                "CAMERA_VARIETY_LOW",
                "warning",
                "Use at least two motivated camera angles on a multi-panel page.",
            ))
            scores["visual_variety"] -= 15

        ordered_panels = {panel.get("panel_id"): panel for panel in panels if isinstance(panel, dict)}
        sequence = page.get("reading_sequence") or panel_ids
        previous_panel: Dict[str, Any] | None = None
        for panel_id in sequence:
            panel = ordered_panels.get(panel_id)
            if not panel or not isinstance(panel.get("event"), dict):
                previous_panel = panel
                continue
            if previous_panel and isinstance(previous_panel.get("event"), dict):
                before = previous_panel["event"]
                after = panel["event"]
                opposite = {
                    ("left_to_right", "right_to_left"),
                    ("right_to_left", "left_to_right"),
                }
                if (
                    before.get("event_type") == "action"
                    and after.get("event_type") == "action"
                    and (before.get("action_direction"), after.get("action_direction")) in opposite
                    and after.get("axis_break") is not True
                ):
                    findings.append(_finding(
                        "UNMARKED_AXIS_REVERSAL",
                        "warning",
                        "Consecutive action panels reverse screen direction without an explicit axis break.",
                        panel_ids=[previous_panel.get("panel_id"), panel.get("panel_id")],
                    ))
                    scores["continuity"] -= 25
                continuity_out = set(before.get("continuity_out", []))
                continuity_in = set(after.get("continuity_in", []))
                if continuity_out and continuity_in and continuity_out.isdisjoint(continuity_in):
                    findings.append(_finding(
                        "CONTINUITY_HANDOFF_MISMATCH",
                        "warning",
                        "Adjacent panels do not share a declared continuity handoff anchor.",
                        panel_ids=[previous_panel.get("panel_id"), panel.get("panel_id")],
                    ))
                    scores["continuity"] -= 15
            previous_panel = panel

        page_area = max(1, page.get("page_size", {}).get("width", 1) * page.get("page_size", {}).get("height", 1))
        important = [panel for panel in panels if panel.get("event", {}).get("importance", 0) >= 4]
        if important:
            strongest = max(important, key=lambda panel: panel.get("event", {}).get("importance", 0))
            if polygon_area(panel_polygon(strongest)) / page_area < 0.16:
                findings.append(_finding(
                    "KEY_EVENT_UNDERSIZED",
                    "warning",
                    "The highest-importance event has too little page area for a strong visual beat.",
                    panel_ids=[strongest.get("panel_id")],
                ))
                scores["page_impact"] -= 20

    lettering = page.get("lettering", [])
    reading_orders = [item.get("reading_order") for item in lettering if isinstance(item, dict)]
    if lettering and (any(value is None for value in reading_orders) or len(set(reading_orders)) != len(reading_orders)):
        findings.append(_finding(
            "LETTERING_ORDER_AMBIGUOUS",
            "warning",
            "Give every lettering item a unique reading_order for predictable balloon and SFX flow.",
        ))
        scores["reading_flow"] -= 20

    page_style = page.get("lettering_style", {})
    for index, item in enumerate(lettering):
        if not isinstance(item, dict) or not isinstance(item.get("box"), dict):
            continue
        lettering_id = item.get("lettering_id", f"letter-{index + 1}")
        fit = fit_lettering_text(item, page_style, project_root)
        if not fit["fits"]:
            findings.append(_finding(
                "LETTERING_OVERFLOW",
                "error",
                "Text cannot fit in its box at the configured minimum font size.",
                panel_ids=[item.get("panel_id")],
                lettering_ids=[lettering_id],
            ))
            scores["readability"] -= 30
            scores["lettering"] -= 30
        if item.get("kind") != "sfx" and len(item.get("text", "").split()) > 35:
            findings.append(_finding(
                "BALLOON_WORD_COUNT_HIGH",
                "warning",
                "A balloon exceeds 35 words; split or tighten it for manga reading speed.",
                panel_ids=[item.get("panel_id")],
                lettering_ids=[lettering_id],
            ))
            scores["readability"] -= 15
        if item.get("kind") == "sfx" and not isinstance(item.get("sound"), dict):
            findings.append(_finding(
                "SFX_MEANING_MISSING",
                "error",
                "SFX requires source, meaning, and intensity so readers can understand the sound treatment.",
                panel_ids=[item.get("panel_id")],
                lettering_ids=[lettering_id],
            ))
            scores["lettering"] -= 25

    if not any(finding["severity"] == "error" for finding in findings):
        findings.append(_finding(
            "HUMAN_APPROVAL_REQUIRED",
            "info",
            "Automated indicators passed their hard checks; a human must still approve story clarity and visual impact.",
        ))

    metrics = {key: max(0, min(100, int(value))) for key, value in scores.items()}
    metrics["overall"] = int(round(sum(metrics.values()) / len(metrics)))
    severities = {finding["severity"] for finding in findings}
    status = "blocked" if "error" in severities else "changes_requested" if "warning" in severities else "review_ready"
    return {
        "schema_version": "1.0.0",
        "review_id": review_id,
        "project_id": project_id,
        "review_type": "page_quality",
        "target": target,
        "status": status,
        "automated": True,
        "approval_required": True,
        "metric_scope": "planning_indicators",
        "metrics": metrics,
        "findings": findings,
    }
