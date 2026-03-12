"""
Citation parsing and formatting engine.
Supports: Academia Română (AR), APA 7th, MLA 9th, Chicago 17th.
"""

import re
from pathlib import Path
from typing import Optional


# Citation pattern: (Author, Year[, p. X])
CITATION_PATTERN = re.compile(
    r'\(([A-ZÀ-Ž][a-zà-ž]+(?:[-\s][A-ZÀ-Ž][a-zà-ž]+)*'
    r'(?:\s(?:și|and|&|et|und)\s[A-ZÀ-Ž][a-zà-ž]+(?:[-\s][A-ZÀ-Ž][a-zà-ž]+)*)?'
    r'(?:\s+et\s+al\.)?)'
    r',\s*(\d{4})'
    r'(?:,\s*(?:pp?\.\s*)([\d\-–]+))?'
    r'\)'
)


class CitationStyle:
    """Base citation style formatter."""
    name: str = ""

    def format_footnote(self, author: str, year: str, title: str = "",
                        publisher: str = "", city: str = "", pages: str | None = None) -> str:
        raise NotImplementedError

    def format_bibliography(self, author: str, year: str, title: str = "",
                           publisher: str = "", city: str = "") -> str:
        raise NotImplementedError


class AcademiaRomanaStyle(CitationStyle):
    """Academia Română — Note de subsol citation style."""
    name = "AR (Note de subsol – Academia Română)"

    def format_footnote(self, author: str, year: str, title: str = "",
                        publisher: str = "", city: str = "", pages: str | None = None) -> str:
        parts = [author]
        if title:
            parts.append(title)
        if publisher:
            parts.append(publisher)
        if city:
            parts.append(city)
        parts.append(year)
        if pages:
            parts.append(f"p. {pages}")
        return ", ".join(parts) + "."

    def format_bibliography(self, author: str, year: str, title: str = "",
                           publisher: str = "", city: str = "") -> str:
        parts = [author]
        if title:
            parts.append(title)
        if city:
            parts.append(city)
        if publisher:
            parts.append(publisher)
        parts.append(year)
        return ", ".join(parts) + "."


class APAStyle(CitationStyle):
    """APA 7th edition citation style."""
    name = "APA 7th"

    def format_footnote(self, author: str, year: str, title: str = "",
                        publisher: str = "", city: str = "", pages: str | None = None) -> str:
        base = f"{author} ({year})."
        if title:
            base += f" {title}."
        if publisher:
            base += f" {publisher}."
        if pages:
            base += f" p. {pages}."
        return base

    def format_bibliography(self, author: str, year: str, title: str = "",
                           publisher: str = "", city: str = "") -> str:
        base = f"{author} ({year})."
        if title:
            base += f" {title}."
        if publisher:
            base += f" {publisher}."
        return base


class MLAStyle(CitationStyle):
    """MLA 9th edition citation style."""
    name = "MLA 9th"

    def format_footnote(self, author: str, year: str, title: str = "",
                        publisher: str = "", city: str = "", pages: str | None = None) -> str:
        base = f"{author}."
        if title:
            base += f" {title}."
        if publisher:
            base += f" {publisher},"
        base += f" {year}."
        if pages:
            base += f" pp. {pages}."
        return base

    def format_bibliography(self, author: str, year: str, title: str = "",
                           publisher: str = "", city: str = "") -> str:
        return self.format_footnote(author, year, title, publisher, city)


class ChicagoStyle(CitationStyle):
    """Chicago 17th edition citation style."""
    name = "Chicago 17th"

    def format_footnote(self, author: str, year: str, title: str = "",
                        publisher: str = "", city: str = "", pages: str | None = None) -> str:
        parts = [author]
        if title:
            parts.append(title)
        location = ""
        if city:
            location += city
        if publisher:
            location += f": {publisher}" if location else publisher
        if location:
            parts.append(f"({location}, {year})")
        else:
            parts.append(f"({year})")
        if pages:
            parts.append(f"{pages}")
        return ", ".join(parts) + "."

    def format_bibliography(self, author: str, year: str, title: str = "",
                           publisher: str = "", city: str = "") -> str:
        base = f"{author}."
        if title:
            base += f" {title}."
        if city and publisher:
            base += f" {city}: {publisher}, {year}."
        elif publisher:
            base += f" {publisher}, {year}."
        else:
            base += f" {year}."
        return base


# Style registry
STYLES = {
    "AR (Note de subsol – Academia Română)": AcademiaRomanaStyle(),
    "APA 7th": APAStyle(),
    "MLA 9th": MLAStyle(),
    "Chicago 17th": ChicagoStyle(),
}


def get_style(name: str) -> CitationStyle:
    """Get a citation style by name."""
    for key, style in STYLES.items():
        if name in key or key in name:
            return style
    return AcademiaRomanaStyle()  # Default


def load_custom_styles(styles_dir: Path) -> dict[str, str]:
    """Load citation style descriptions from .md files."""
    custom = {}
    styles_dir = Path(styles_dir)
    if styles_dir.exists():
        for md_file in styles_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            # Extract title from first heading
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            title = title_match.group(1) if title_match else md_file.stem
            custom[title] = content
    return custom


def find_citations(text: str) -> list[dict]:
    """Find all citation markers in text.

    Returns list of dicts with keys: author, year, pages, start, end, full_match
    """
    results = []
    for match in CITATION_PATTERN.finditer(text):
        results.append({
            "author": match.group(1),
            "year": match.group(2),
            "pages": match.group(3),
            "start": match.start(),
            "end": match.end(),
            "full_match": match.group(0),
        })
    return results


def get_available_styles() -> list[str]:
    """Return list of available citation style names."""
    return list(STYLES.keys())
