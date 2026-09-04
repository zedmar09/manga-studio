from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, BinaryIO, Dict, Tuple


class ImageInspectionError(ValueError):
    pass


def _read_exact(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ImageInspectionError("image header is truncated")
    return data


def _inspect_png(handle: BinaryIO) -> Dict[str, Any]:
    header = _read_exact(handle, 26)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ImageInspectionError("invalid PNG signature or IHDR chunk")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", header[16:26])
    color_modes = {
        0: "bilevel" if bit_depth == 1 else "grayscale",
        2: "rgb",
        3: "indexed",
        4: "grayscale_alpha",
        6: "rgba",
    }
    if color_type not in color_modes:
        raise ImageInspectionError(f"unsupported PNG color type {color_type}")
    return {
        "format": "png",
        "width": width,
        "height": height,
        "color_mode": color_modes[color_type],
        "bit_depth": bit_depth,
        "has_alpha": color_type in {4, 6},
    }


def _inspect_jpeg(handle: BinaryIO) -> Dict[str, Any]:
    if _read_exact(handle, 2) != b"\xff\xd8":
        raise ImageInspectionError("invalid JPEG signature")
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while True:
        marker_prefix = handle.read(1)
        if not marker_prefix:
            raise ImageInspectionError("JPEG has no supported start-of-frame marker")
        if marker_prefix != b"\xff":
            continue
        marker = _read_exact(handle, 1)[0]
        while marker == 0xFF:
            marker = _read_exact(handle, 1)[0]
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        segment_length = struct.unpack(">H", _read_exact(handle, 2))[0]
        if segment_length < 2:
            raise ImageInspectionError("invalid JPEG segment length")
        if marker in start_of_frame:
            frame = _read_exact(handle, 6)
            precision, height, width, components = struct.unpack(">BHHB", frame)
            color_mode = {1: "grayscale", 3: "rgb", 4: "cmyk"}.get(components, "unknown")
            return {
                "format": "jpeg",
                "width": width,
                "height": height,
                "color_mode": color_mode,
                "bit_depth": precision,
                "has_alpha": False,
            }
        handle.seek(segment_length - 2, 1)


def _inspect_webp(handle: BinaryIO) -> Dict[str, Any]:
    header = _read_exact(handle, 30)
    if header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        raise ImageInspectionError("invalid WebP signature")
    chunk = header[12:16]
    if chunk == b"VP8X":
        flags = header[20]
        width = 1 + int.from_bytes(header[24:27], "little")
        height = 1 + int.from_bytes(header[27:30], "little")
        has_alpha = bool(flags & 0x10)
    elif chunk == b"VP8 " and header[23:26] == b"\x9d\x01\x2a":
        width = struct.unpack("<H", header[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", header[28:30])[0] & 0x3FFF
        has_alpha = False
    elif chunk == b"VP8L" and header[20] == 0x2F:
        packed = int.from_bytes(header[21:25], "little")
        width = (packed & 0x3FFF) + 1
        height = ((packed >> 14) & 0x3FFF) + 1
        has_alpha = bool((packed >> 28) & 1)
    else:
        raise ImageInspectionError("unsupported or truncated WebP header")
    return {
        "format": "webp",
        "width": width,
        "height": height,
        "color_mode": "rgba" if has_alpha else "rgb",
        "bit_depth": 8,
        "has_alpha": has_alpha,
    }


def _tiff_value(
    handle: BinaryIO,
    endian: str,
    value_type: int,
    count: int,
    raw_value: bytes,
) -> Tuple[int, ...]:
    sizes = {1: 1, 3: 2, 4: 4}
    formats = {1: "B", 3: "H", 4: "I"}
    if value_type not in sizes or count < 1:
        return ()
    size = sizes[value_type] * count
    if size <= 4:
        data = raw_value[:size]
    else:
        offset = struct.unpack(endian + "I", raw_value)[0]
        position = handle.tell()
        handle.seek(offset)
        data = _read_exact(handle, size)
        handle.seek(position)
    return struct.unpack(endian + formats[value_type] * count, data)


def _inspect_tiff(handle: BinaryIO) -> Dict[str, Any]:
    header = _read_exact(handle, 8)
    if header[:2] == b"II":
        endian = "<"
    elif header[:2] == b"MM":
        endian = ">"
    else:
        raise ImageInspectionError("invalid TIFF byte order")
    if struct.unpack(endian + "H", header[2:4])[0] != 42:
        raise ImageInspectionError("unsupported TIFF header")
    handle.seek(struct.unpack(endian + "I", header[4:8])[0])
    count = struct.unpack(endian + "H", _read_exact(handle, 2))[0]
    tags: Dict[int, Tuple[int, ...]] = {}
    for _ in range(count):
        entry = _read_exact(handle, 12)
        tag, value_type, value_count = struct.unpack(endian + "HHI", entry[:8])
        if tag in {256, 257, 258, 262, 277, 338}:
            tags[tag] = _tiff_value(handle, endian, value_type, value_count, entry[8:12])
    try:
        width, height = tags[256][0], tags[257][0]
    except (KeyError, IndexError):
        raise ImageInspectionError("TIFF width or height tag is missing")
    bit_depth = tags.get(258, (8,))[0]
    photometric = tags.get(262, (-1,))[0]
    samples = tags.get(277, (1,))[0]
    has_alpha = bool(tags.get(338)) or (photometric == 2 and samples > 3)
    if photometric in {0, 1}:
        color_mode = "grayscale_alpha" if has_alpha else ("bilevel" if bit_depth == 1 else "grayscale")
    elif photometric == 2:
        color_mode = "rgba" if has_alpha else "rgb"
    elif photometric == 3:
        color_mode = "indexed"
    elif photometric == 5:
        color_mode = "cmyk"
    else:
        color_mode = "unknown"
    return {
        "format": "tiff",
        "width": width,
        "height": height,
        "color_mode": color_mode,
        "bit_depth": bit_depth,
        "has_alpha": has_alpha,
    }


def inspect_image(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ImageInspectionError(f"generated image is missing: {path}")
    with path.open("rb") as handle:
        signature = _read_exact(handle, 12)
        handle.seek(0)
        if signature.startswith(b"\x89PNG\r\n\x1a\n"):
            result = _inspect_png(handle)
        elif signature.startswith(b"\xff\xd8"):
            result = _inspect_jpeg(handle)
        elif signature[:4] == b"RIFF" and signature[8:12] == b"WEBP":
            result = _inspect_webp(handle)
        elif signature[:4] in {b"II*\x00", b"MM\x00*"}:
            result = _inspect_tiff(handle)
        else:
            raise ImageInspectionError("unsupported image signature; expected PNG, JPEG, WebP, or TIFF")
    result["size_bytes"] = path.stat().st_size
    return result


def compare_to_job(file_info: Dict[str, Any], job: Dict[str, Any]) -> list[Dict[str, str]]:
    findings: list[Dict[str, str]] = []
    expected = job.get("output_spec", {})
    for field in ("format", "width", "height"):
        if file_info.get(field) != expected.get(field):
            findings.append({
                "severity": "error",
                "code": f"{field}_mismatch",
                "message": f"Generated {field} {file_info.get(field)!r} does not match required {expected.get(field)!r}.",
            })
    if file_info.get("has_alpha") and expected.get("alpha_allowed") is False:
        findings.append({
            "severity": "error",
            "code": "alpha_not_allowed",
            "message": "Generated image contains an alpha channel, but the image job prohibits alpha.",
        })
    actual_mode = file_info.get("color_mode")
    expected_mode = expected.get("color_mode")
    compatible = actual_mode == expected_mode or (expected_mode == "grayscale" and actual_mode == "bilevel")
    if not compatible:
        findings.append({
            "severity": "warning",
            "code": "color_mode_review",
            "message": (
                f"Generated container mode {actual_mode!r} differs from required {expected_mode!r}; "
                "a human must confirm that the visible artwork still follows the manga palette."
            ),
        })
    palette = job.get("manga_style", {}).get("palette")
    if palette == "black-and-white" and actual_mode not in {"bilevel", "grayscale", "grayscale_alpha"}:
        findings.append({
            "severity": "warning",
            "code": "monochrome_visual_review",
            "message": "The file container can carry color; human visual review must confirm strictly black-and-white artwork.",
        })
    return findings
