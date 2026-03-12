"""
Bibliography generation, validation, and import from .bib files.
"""

import re
import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.citation_engine import CitationStyle, get_style

logger = logging.getLogger(__name__)


def validate_entry(entry: str) -> dict:
    """Validate a bibliography entry for completeness.

    Returns dict with keys: valid, has_author, has_year, has_title, warnings
    """
    result = {
        "entry": entry,
        "valid": False,
        "has_author": False,
        "has_year": False,
        "has_title": False,
        "warnings": [],
    }

    # Check for year
    if re.search(r'\b(19\d{2}|20\d{2})\b', entry):
        result["has_year"] = True
    else:
        result["warnings"].append("Lipsește anul publicării")

    # Check for author (at least a capitalized name)
    if re.match(r'^[A-ZÀ-Ž]', entry.strip()):
        result["has_author"] = True
    else:
        result["warnings"].append("Lipsește autorul")

    # Check for title (meaningful length)
    if len(entry.strip()) > 30:
        result["has_title"] = True
    else:
        result["warnings"].append("Intrarea pare incompletă")

    result["valid"] = result["has_author"] and result["has_year"] and result["has_title"]
    return result


def validate_bibliography(entries: list[str]) -> list[dict]:
    """Validate all bibliography entries."""
    return [validate_entry(e) for e in entries if e.strip()]


def validate_entry_online(entry: str) -> dict:
    """Validate a bibliography entry against online APIs (Crossref, OpenLibrary)."""
    import requests

    result = validate_entry(entry)

    # Try DOI validation
    doi_match = re.search(r'(10\.\d{4,}/\S+)', entry)
    if doi_match:
        doi = doi_match.group(1).rstrip('.')
        try:
            resp = requests.get(f"https://api.crossref.org/works/{doi}", timeout=10)
            if resp.status_code == 200:
                result["doi_valid"] = True
                result["valid"] = True
                return result
        except Exception:
            pass

    # Try ISBN validation
    isbn_match = re.search(r'(?:ISBN[:\s-]*)?(\d{10,13})', entry)
    if isbn_match:
        isbn = isbn_match.group(1)
        try:
            resp = requests.get(
                f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json",
                timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                result["isbn_valid"] = True
                result["valid"] = True
                return result
        except Exception:
            pass

    # Try URL validation
    url_match = re.search(r'https?://\S+', entry)
    if url_match:
        try:
            resp = requests.head(url_match.group(0), timeout=10, allow_redirects=True)
            result["url_reachable"] = resp.status_code < 400
        except Exception:
            result["url_reachable"] = False

    return result


def validate_bibliography_online(entries: list[str], max_workers: int = 5) -> list[dict]:
    """Validate all entries in parallel using online APIs."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(validate_entry_online, e): e for e in entries if e.strip()}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                results.append(validate_entry(futures[future]))
    return results


def parse_bib_file(filepath: Path) -> list[str]:
    """Parse a .bib file and return formatted bibliography entries."""
    try:
        import bibtexparser
    except ImportError:
        return _parse_bib_manual(filepath)

    with open(filepath, encoding="utf-8") as f:
        bib_db = bibtexparser.load(f)

    entries = []
    for entry in bib_db.entries:
        author = entry.get("author", "").replace(" and ", ", ")
        title = entry.get("title", "").strip("{}")
        year = entry.get("year", "")
        publisher = entry.get("publisher", "")
        journal = entry.get("journal", "")
        address = entry.get("address", "")

        if journal:
            formatted = f'{author}, "{title}", {journal}'
            if year:
                formatted += f", {year}"
        else:
            formatted = f"{author}, {title}"
            if publisher:
                formatted += f", {publisher}"
            if address:
                formatted += f", {address}"
            if year:
                formatted += f", {year}"

        entries.append(formatted + ".")

    return entries


def _parse_bib_manual(filepath: Path) -> list[str]:
    """Simple .bib parser without bibtexparser."""
    content = Path(filepath).read_text(encoding="utf-8")
    entries = []
    for match in re.finditer(r'@\w+\{[^@]+\}', content, re.DOTALL):
        block = match.group(0)
        fields = {}
        for field_match in re.finditer(r'(\w+)\s*=\s*\{([^}]*)\}', block):
            fields[field_match.group(1).lower()] = field_match.group(2)

        author = fields.get("author", "").replace(" and ", ", ")
        title = fields.get("title", "")
        year = fields.get("year", "")
        publisher = fields.get("publisher", "")

        if author and title:
            line = f"{author}, {title}"
            if publisher:
                line += f", {publisher}"
            if year:
                line += f", {year}"
            entries.append(line + ".")

    return entries


def format_entries_for_style(entries: list[str], style: CitationStyle) -> list[str]:
    """Re-format bibliography entries according to the selected style."""
    # For now, return as-is since entries are typically already formatted
    # Full re-parsing would require structured entry data
    return entries


def search_crossref(topic: str, rows: int = 10) -> list[str]:
    """Search Crossref API for real academic sources on a topic."""
    import requests

    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query": topic, "rows": rows, "sort": "relevance"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        items = resp.json().get("message", {}).get("items", [])
        entries = []
        for item in items:
            authors = item.get("author", [])
            author_str = ", ".join(
                f"{a.get('family', '')}, {a.get('given', '')}" for a in authors[:3]
            )
            if len(authors) > 3:
                author_str += " et al."
            title = " ".join(item.get("title", [""]))
            year = ""
            if "published-print" in item:
                year = str(item["published-print"]["date-parts"][0][0])
            elif "published-online" in item:
                year = str(item["published-online"]["date-parts"][0][0])
            journal = item.get("container-title", [""])[0]

            if author_str and title:
                entry = f'{author_str}, "{title}"'
                if journal:
                    entry += f", {journal}"
                if year:
                    entry += f", {year}"
                entries.append(entry + ".")

        return entries
    except Exception:
        return []
