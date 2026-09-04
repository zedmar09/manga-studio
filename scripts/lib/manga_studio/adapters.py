from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol, Tuple


class SourceAdapter(Protocol):
    name: str
    extensions: Tuple[str, ...]

    def normalize(self, raw: bytes, source: Path) -> str:
        """Return a normalized derivative without modifying source bytes."""


def _decode_utf8(raw: bytes, source: Path, adapter_name: str) -> str:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{adapter_name} adapter could not decode '{source}' as UTF-8; "
            "preserve it and configure a future encoding adapter."
        ) from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True)
class PlainTextAdapter:
    name: str = "plain_text"
    extensions: Tuple[str, ...] = (".txt",)

    def normalize(self, raw: bytes, source: Path) -> str:
        return _decode_utf8(raw, source, self.name)


@dataclass(frozen=True)
class MarkdownAdapter:
    name: str = "markdown"
    extensions: Tuple[str, ...] = (".md", ".markdown")

    def normalize(self, raw: bytes, source: Path) -> str:
        return _decode_utf8(raw, source, self.name)


ADAPTERS: Tuple[SourceAdapter, ...] = (PlainTextAdapter(), MarkdownAdapter())
ADAPTERS_BY_NAME: Dict[str, SourceAdapter] = {adapter.name: adapter for adapter in ADAPTERS}
ADAPTERS_BY_EXTENSION: Dict[str, SourceAdapter] = {
    extension: adapter for adapter in ADAPTERS for extension in adapter.extensions
}


def adapter_for_extension(extension: str) -> Optional[SourceAdapter]:
    return ADAPTERS_BY_EXTENSION.get(extension.lower())


def adapter_by_name(name: str) -> SourceAdapter:
    try:
        return ADAPTERS_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"Source adapter is not installed: {name}") from exc
