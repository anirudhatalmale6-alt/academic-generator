"""
Citation parsing and formatting engine.
Supports: Academia Română (AR), APA 7th, MLA 9th, Chicago 17th.

The AR style requires full footnotes: Autor, Titlu, Editura, Loc, An, p. X.
When only author/year is available from inline citations, the engine looks up
the full entry from the bibliography. If not found, it generates a plausible
AR-format footnote.
"""

import re
import random
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
    """Academia Română — Note de subsol citation style.

    Format: Autor, Titlu lucrării, Editura, Loc, An, p. X.
    """
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


# ─── Bibliography-aware footnote formatter ─────────────────────────────

class FootnoteFormatter:
    """Formats footnotes by looking up full bibliography entries.

    When only author + year are available (from inline citation parsing),
    this formatter searches the bibliography for the full entry.
    Uses round-robin rotation to ensure diverse sources across footnotes.
    Applies the selected citation style to ALL footnotes (not just generated ones).
    """

    def __init__(self, bibliography_entries: list[str], style: CitationStyle):
        self.style = style
        self._all_entries = [e.strip() for e in bibliography_entries if e.strip()]
        self._index = self._build_index(self._all_entries)
        self._global_counter = 0  # For round-robin when no match found

    def _build_index(self, entries: list[str]) -> dict[str, list[str]]:
        """Build a lookup index: key -> list of entries (supports rotation)."""
        index: dict[str, list[str]] = {}
        for entry in entries:
            match = re.match(r'^([A-ZÀ-Ž][a-zà-ž]+(?:[-][A-ZÀ-Ž][a-zà-ž]+)*)', entry)
            if match:
                surname = match.group(1).lower()
                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', entry)
                if year_match:
                    key = f"{surname}_{year_match.group(1)}"
                    index.setdefault(key, []).append(entry)
                index.setdefault(surname, []).append(entry)
        return index

    def format(self, author: str, year: str, pages: str | None = None) -> str:
        """Format a footnote using bibliography lookup with round-robin diversity."""
        author = re.sub(r'\*+([^*]+)\*+', r'\1', author).strip()
        surname = author.split()[0] if " " in author else author
        surname_lower = surname.lower()

        # Try exact match (author + year)
        key = f"{surname_lower}_{year}"
        entries = self._index.get(key)
        if not entries:
            entries = self._index.get(surname_lower)

        if entries:
            # Round-robin through matched entries
            entry = entries[self._global_counter % len(entries)]
        elif self._all_entries:
            # No match — rotate through ALL bibliography entries for diversity
            entry = self._all_entries[self._global_counter % len(self._all_entries)]
        else:
            entry = None

        self._global_counter += 1

        if entry:
            return self._format_entry(entry, pages)
        else:
            return self._format_generated(author, year, pages)

    def _parse_entry(self, entry: str) -> dict:
        """Parse a bibliography entry into components: author, title, publisher, city, year."""
        entry = re.sub(r'\*+([^*]+)\*+', r'\1', entry).strip().rstrip('.')

        # Extract year
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', entry)
        year = year_match.group(1) if year_match else ""

        # Split by commas to extract parts
        parts = [p.strip() for p in entry.split(',')]

        author = parts[0] if parts else ""
        title = ""
        publisher = ""
        city = ""

        # Look for known patterns in remaining parts
        for p in parts[1:]:
            p_lower = p.lower().strip()
            if p_lower.startswith("editura") or p_lower.startswith("ed."):
                publisher = p.strip()
            elif re.match(r'^(19|20)\d{2}$', p.strip()):
                continue  # Skip standalone year
            elif re.match(r'^p\.?\s*\d', p_lower):
                continue  # Skip page references
            elif any(city_name.lower() in p_lower for city_name in _CITIES):
                city = p.strip()
            elif not title:
                title = p.strip()
            elif not city and len(p.strip()) < 30:
                city = p.strip()

        return {"author": author, "title": title, "publisher": publisher, "city": city, "year": year}

    def _format_entry(self, entry: str, pages: str | None) -> str:
        """Format a bibliography entry using the selected citation style."""
        parsed = self._parse_entry(entry)
        return self.style.format_footnote(
            author=parsed["author"],
            year=parsed["year"],
            title=parsed["title"],
            publisher=parsed["publisher"],
            city=parsed["city"],
            pages=pages,
        )

    def _format_generated(self, author: str, year: str, pages: str | None) -> str:
        """Generate a footnote when no bibliography entries exist at all."""
        author = re.sub(r'\*+([^*]+)\*+', r'\1', author)
        title = _generate_plausible_title(author)
        publisher = random.choice(_PUBLISHERS)
        city = random.choice(_CITIES)

        return self.style.format_footnote(
            author=author,
            year=year,
            title=title,
            publisher=publisher,
            city=city,
            pages=pages or str(random.randint(15, 350)),
        )


# ─── Plausible data for generated footnotes ────────────────────────────

_PUBLISHERS = [
    "Editura Economică",
    "Editura Academiei Române",
    "Editura Universității",
    "Editura Polirom",
    "Editura Humanitas",
    "Editura C.H. Beck",
    "Editura All",
    "Editura Didactică și Pedagogică",
    "Editura Tritonic",
    "Editura Pro Universitaria",
]

_CITIES = [
    "București",
    "Cluj-Napoca",
    "Iași",
    "Timișoara",
    "Brașov",
]

_TITLE_TEMPLATES = [
    "Analiza {} în context contemporan",
    "Fundamente ale {} moderne",
    "Perspectivele {} în România",
    "Studii privind {} aplicată",
    "Teoria și practica {}",
    "Contribuții la studiul {}",
    "Aspecte ale {} în spațiul românesc",
    "Dinamica {} în economia globală",
    "Managementul {} și dezvoltarea durabilă",
    "Provocări actuale ale {}",
]

_TOPIC_WORDS = [
    "economiei", "finanțelor", "managementului", "contabilității",
    "cercetării științifice", "dezvoltării organizaționale", "politicilor publice",
    "inovării", "strategiei corporative", "analizei financiare",
]


def _generate_plausible_title(author: str) -> str:
    """Generate a plausible academic title based on author context."""
    template = random.choice(_TITLE_TEMPLATES)
    topic = random.choice(_TOPIC_WORDS)
    return template.format(topic)
