"""
Extract text from guideline files (PDF, DOCX, TXT, MD).
Used to inject university/faculty guidelines into AI prompts.
"""

import re
from pathlib import Path
from typing import Optional


def extract_text(filepath: Path) -> str:
    """Extract text content from a file based on its extension."""
    filepath = Path(filepath)
    suffix = filepath.suffix.lower()

    extractors = {
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".txt": _extract_text_file,
        ".md": _extract_text_file,
    }

    extractor = extractors.get(suffix)
    if extractor is None:
        return ""

    try:
        return extractor(filepath)
    except Exception as e:
        return f"[Eroare la citirea fișierului {filepath.name}: {e}]"


def _extract_pdf(filepath: Path) -> str:
    """Extract text from PDF using pdfplumber (better for tables) with PyPDF2 fallback."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        if text_parts:
            return "\n\n".join(text_parts)
    except ImportError:
        pass

    # Fallback to PyPDF2
    from PyPDF2 import PdfReader
    reader = PdfReader(str(filepath))
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _extract_docx(filepath: Path) -> str:
    """Extract text from DOCX file."""
    from docx import Document
    doc = Document(str(filepath))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    return "\n".join(text_parts)


def _extract_text_file(filepath: Path) -> str:
    """Extract text from plain text / markdown file."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            return filepath.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return filepath.read_text(encoding="utf-8", errors="replace")


def extract_formatting_rules(text: str) -> dict:
    """Extract formatting rules from guide text."""
    rules = {
        "font": None,
        "size": None,
        "spacing": None,
        "margins": None,
        "alignment": None,
        "indent": None,
        "citation_style": None,
    }

    if re.search(r'Times New Roman', text, re.IGNORECASE):
        rules["font"] = "Times New Roman"
    size_match = re.search(r'(\d+)\s*(?:pt|punct)', text, re.IGNORECASE)
    if size_match:
        rules["size"] = int(size_match.group(1))
    spacing_match = re.search(r'(?:spațiere|interlinie|spacing)[:\s]*(\d[.,]?\d?)', text, re.IGNORECASE)
    if spacing_match:
        rules["spacing"] = float(spacing_match.group(1).replace(',', '.'))
    if re.search(r'justify|aliniere.*stânga.*dreapta|justified', text, re.IGNORECASE):
        rules["alignment"] = "justified"
    indent_match = re.search(r'(?:indent|alineat|paragraf)[:\s]*(\d[.,]?\d?)\s*cm', text, re.IGNORECASE)
    if indent_match:
        rules["indent"] = float(indent_match.group(1).replace(',', '.'))
    if re.search(r'Academia\s+Român[ăa]|AR\b|note\s+de\s+subsol', text, re.IGNORECASE):
        rules["citation_style"] = "AR"
    elif re.search(r'\bAPA\b', text, re.IGNORECASE):
        rules["citation_style"] = "APA"

    return {k: v for k, v in rules.items() if v is not None}


def scan_guides_directory(base_dir: Path) -> dict[str, dict[str, list[Path]]]:
    """Scan the ghiduri_academice/ directory structure.

    Returns: {university_name: {faculty_name: [guide_file_paths]}}
    """
    base_dir = Path(base_dir)
    structure = {}

    if not base_dir.exists():
        return structure

    for univ_dir in sorted(base_dir.iterdir()):
        if not univ_dir.is_dir():
            continue
        univ_name = univ_dir.name
        structure[univ_name] = {}

        for item in sorted(univ_dir.iterdir()):
            if item.is_dir():
                # Faculty subdirectory
                faculty_name = item.name
                guides = list(item.glob("*"))
                guides = [g for g in guides if g.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
                if guides:
                    structure[univ_name][faculty_name] = guides
            elif item.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}:
                # Guide directly under university (general)
                if "GENERAL" not in structure[univ_name]:
                    structure[univ_name]["GENERAL"] = []
                structure[univ_name]["GENERAL"].append(item)

    return structure
