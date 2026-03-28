from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageResult:
    page_number: int
    text: str
    method: str  # "native" | "ocr" | "spatial" | "table_aware"


class BaseProvider(ABC):
    name: str

    @abstractmethod
    def extract(self, path: Path, max_pages: int | None = None) -> list[PageResult]:
        """Extrai texto por pagina. max_pages=None extrai todas."""
        ...
