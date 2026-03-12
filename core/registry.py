"""
Document registry — tracks all generated documents in a local JSON file.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class DocumentRegistry:
    """Manages the local JSON registry of generated documents."""

    def __init__(self, registry_path: Path):
        self.path = Path(registry_path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def add(
        self,
        code: str,
        title: str,
        doc_type: str,
        language: str,
        pages: int,
        citation_style: str,
        output_path: str,
        metadata: dict | None = None,
    ):
        """Register a newly generated document."""
        self._data[code] = {
            "code": code,
            "title": title,
            "type": doc_type,
            "language": language,
            "pages": pages,
            "citation_style": citation_style,
            "created_at": datetime.now().isoformat(),
            "output_path": output_path,
            "meta": metadata or {},
        }
        self._save()

    def get(self, code: str) -> Optional[dict]:
        """Get a document entry by code."""
        return self._data.get(code)

    def search(self, query: str = "", doc_type: str = "") -> list[dict]:
        """Search registry by code, title, or type."""
        results = []
        for entry in self._data.values():
            if query:
                q = query.lower()
                if q not in entry["code"].lower() and q not in entry["title"].lower():
                    continue
            if doc_type and entry["type"] != doc_type:
                continue
            results.append(entry)
        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)

    def list_all(self) -> list[dict]:
        """Return all registry entries sorted by date."""
        return sorted(self._data.values(), key=lambda x: x.get("created_at", ""), reverse=True)

    def remove(self, code: str) -> bool:
        """Remove a document from the registry."""
        if code in self._data:
            del self._data[code]
            self._save()
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._data)
