"""
Prompt construction pipeline for AI content generation.
Builds context-aware prompts with guide injection and section-specific instructions.
"""

import re
from pathlib import Path
from typing import Optional

from core.guide_reader import extract_text, extract_formatting_rules
from core.citation_engine import get_style


def calculate_section_length(section_name: str, total_pages: int, total_sections: int, detail_level: str = "Standard") -> dict:
    """Estimate content length requirements for a section.

    Uses total_pages and total_sections to distribute page budget evenly,
    with small adjustments for intro/conclusion (shorter) vs chapters (longer).
    """
    from core.formatting import DETAIL_MULTIPLIERS

    multiplier = DETAIL_MULTIPLIERS.get(detail_level, 1.0)
    name_lower = section_name.lower()

    # Base: divide pages evenly among sections, then adjust by type
    base_pages_per_section = total_pages / max(total_sections, 1)

    if any(kw in name_lower for kw in ["introducere", "argument", "introduction"]):
        weight = 0.6  # Intro is shorter
    elif any(kw in name_lower for kw in ["conclu", "conclusion"]):
        weight = 0.5  # Conclusions are shorter
    elif any(kw in name_lower for kw in ["rezumat", "abstract", "summary"]):
        weight = 0.3  # Abstract is very short
    elif any(kw in name_lower for kw in ["capitol", "chapter", "capitolul"]):
        weight = 1.3  # Chapters get a bit more
    else:
        weight = 1.0

    estimated_pages = max(0.5, base_pages_per_section * weight * multiplier)
    # ~250 words per page, ~3 paragraphs per page
    word_count = int(estimated_pages * 250)
    paragraphs = max(2, int(estimated_pages * 3))
    sentences_per_paragraph = 5

    return {
        "estimated_pages": round(estimated_pages, 1),
        "paragraphs": paragraphs,
        "sentences_per_paragraph": sentences_per_paragraph,
        "word_count": word_count,
        "max_tokens": max(200, int(word_count * 1.5)),  # Token budget (~1.5 tokens/word)
    }


def build_system_prompt(provider: str, language: str = "Română", tone: str = "Formal academic") -> str:
    """Build provider-specific system prompt."""
    base = (
        f"Ești un cercetător academic de elită cu experiență vastă în redactarea lucrărilor științifice. "
        f"Scrii în limba {language}, cu ton {tone.lower()}. "
        f"Respectă cu strictețe următoarele reguli:\n"
        f"- Scrie DOAR proză academică continuă — paragraf după paragraf\n"
        f"- NU folosi markdown (bold, italic, bullets, liste numerotate)\n"
        f"- NU folosi texte meta ('Voi prezenta...', 'În continuare...', 'Iată...')\n"
        f"- NU inventa surse bibliografice — folosește doar citări în format (Autor, An) sau (Autor, An, p. X)\n"
        f"- Fiecare paragraf trebuie să aibă 5-8 propoziții\n"
        f"- Folosește diacriticele românești corect: ă, â, î, ș, ț\n"
        f"- Structurează conținutul cu titluri de secțiune folosind # pentru H1, ## pentru H2, ### pentru H3\n"
    )

    if provider == "Claude":
        base += (
            "\n- Scrie direct, fără introduceri sau concluzii artificiale\n"
            "- Nu adăuga comentarii sau explicații despre textul generat\n"
        )
    elif provider in ("OpenAI", "Gemini"):
        base += (
            "\n- IMPORTANT: Nu fabrica nicio sursă bibliografică\n"
            "- Folosește citări inline (Autor, An, p. X) pe care le cunoști ca reale\n"
            "- Nu adăuga prefațe sau postfețe la conținut\n"
        )

    return base


def build_section_prompt(
    section_name: str,
    title: str,
    doc_type: str,
    language: str,
    total_pages: int,
    total_sections: int,
    detail_level: str,
    citation_style_name: str,
    footnotes_per_page: int,
    keywords: str = "",
    other_details: str = "",
    guides_text: str = "",
    formatting_rules: dict | None = None,
    bibliography_entries: list[str] | None = None,
    previous_sections: list[str] | None = None,
) -> str:
    """Build the complete prompt for generating a document section."""

    length = calculate_section_length(section_name, total_pages, total_sections, detail_level)
    target_citations = max(1, int(footnotes_per_page * length["estimated_pages"]))

    # Build bibliography authors hint
    authors_hint = ""
    if bibliography_entries:
        authors = set()
        for entry in bibliography_entries[:30]:
            match = re.match(r'^([A-ZÀ-Ž][a-zà-ž]+(?:[-\s][A-ZÀ-Ž][a-zà-ž]+)*)', entry.strip())
            if match:
                authors.add(match.group(1))
        if authors:
            authors_hint = "Autori disponibili pentru citare: " + ", ".join(sorted(authors)[:20])

    # Build context from previous sections
    context_hint = ""
    if previous_sections:
        context_hint = (
            "\n\nSecțiuni generate anterior (pentru coerență):\n"
            + "\n".join(f"- {s}" for s in previous_sections[-5:])
        )

    # Build formatting rules text
    rules_text = ""
    if formatting_rules:
        rules_parts = []
        for key, val in formatting_rules.items():
            rules_parts.append(f"  - {key}: {val}")
        rules_text = "\nReguli de formatare extrase din ghiduri:\n" + "\n".join(rules_parts)

    # Build guides injection
    guides_section = ""
    if guides_text:
        # Truncate to avoid exceeding context limits
        max_guide_chars = 8000
        truncated = guides_text[:max_guide_chars]
        if len(guides_text) > max_guide_chars:
            truncated += "\n[... ghid trunchiat ...]"
        guides_section = (
            f"\n\n--- GHIDURI ACADEMICE (OBLIGATORIU de respectat) ---\n"
            f"{truncated}\n"
            f"--- SFÂRȘIT GHIDURI ---\n"
            f"\nIMPORTANT: NU COPIA text din ghiduri! Folosește-le doar ca reguli de formatare și structură.\n"
        )

    prompt = f"""Scrie conținut academic profesional în limba {language} pentru secțiunea '{section_name}'
din lucrarea de {doc_type} intitulată '{title}'.

LIMITĂ STRICTĂ DE LUNGIME (OBLIGATORIU):
- EXACT {length['word_count']} cuvinte (±10%). NU DEPĂȘI această limită!
- EXACT {length['paragraphs']} paragrafe, fiecare de {length['sentences_per_paragraph']} propoziții
- Aceasta corespunde la aproximativ {length['estimated_pages']} pagini
- Documentul total are {total_pages} pagini, iar aceasta este una din {total_sections} secțiuni
- Dacă scrii mai mult de {int(length['word_count'] * 1.1)} cuvinte, textul va fi TRUNCHIAT

CERINȚE DE CITARE:
- Include {target_citations} citări în format (Autor, An) sau (Autor, An, p. X)
- Stil de citare: {citation_style_name}
- NU folosi asteriscuri (*) în jurul titlurilor din citări — scrie text simplu
{authors_hint}

CERINȚE DE STRUCTURĂ:
- Folosește # pentru titluri principale, ## pentru subtitluri, ### pentru sub-subtitluri
- Scrie proză academică continuă, fără liste sau bullets
- Fiecare paragraf: {length['sentences_per_paragraph']} propoziții complete
- Ton formal, obiectiv, critic
- Folosește diacriticele românești corect (dacă scrii în română)

INTERZIS:
- Asteriscuri (*text*) sau orice formatare markdown — scrie TEXT SIMPLU
- Liste cu bullets sau numerotate
- Texte meta ("Voi prezenta...", "În această secțiune...")
- Fabricarea de surse bibliografice
- Copierea textului din ghiduri
- Depășirea limitei de {length['word_count']} cuvinte
{rules_text}
{context_hint}"""

    if keywords:
        prompt += f"\n\nCuvinte cheie / teme de acoperit: {keywords}"

    if other_details:
        prompt += f"\n\nDetalii suplimentare de la utilizator: {other_details}"

    prompt += guides_section

    prompt += f"\n\nScrie DOAR conținutul academic pentru '{section_name}':"

    return prompt


def build_abstract_prompt(title: str, doc_type: str, language: str, chapters: list[str]) -> str:
    """Build prompt for generating the abstract/summary."""
    chapters_text = "\n".join(f"- {ch}" for ch in chapters)
    return f"""Scrie un rezumat academic (abstract) de 200-300 de cuvinte în limba {language}
pentru lucrarea de {doc_type} intitulată '{title}'.

Structura lucrării:
{chapters_text}

Cerințe:
- Un singur paragraf coerent
- Prezintă: scopul, metodologia, principalele constatări, concluzii
- Ton formal, obiectiv
- Fără citări sau referințe
- Fără markdown sau formatare specială

Scrie DOAR rezumatul:"""


def build_toc_prompt(title: str, doc_type: str, language: str, page_count: int) -> str:
    """Build prompt for auto-generating a table of contents structure."""
    return f"""Generează o structură de cuprins (table of contents) pentru o lucrare de {doc_type}
în limba {language}, intitulată '{title}', de aproximativ {page_count} pagini.

Cerințe:
- Include Introducere, 3-5 capitole cu subcapitole, Concluzii, Bibliografie
- Fiecare capitol principal să aibă 2-4 subcapitole
- Titlurile să fie academice, specifice temei
- Returnează DOAR lista de capitole, câte unul pe linie
- Marchează nivelurile: fără prefix = capitol principal, TAB + text = subcapitol

Exemplu format:
Introducere
Capitolul I – Titlu capitol
\tSubcapitol 1.1
\tSubcapitol 1.2
Capitolul II – Titlu capitol
\tSubcapitol 2.1

Generează cuprinsul:"""


def build_bibliography_prompt(
    title: str,
    doc_type: str,
    language: str,
    min_sources: int,
    citation_style_name: str,
    topic_keywords: str = "",
) -> str:
    """Build prompt for generating bibliography entries."""
    return f"""Generează o bibliografie academică de MINIM {min_sources} surse pentru o lucrare de {doc_type}
intitulată '{title}', în limba {language}.

Stil de citare: {citation_style_name}

Cerințe:
- DOAR surse REALE, verificabile — cărți și articole existente
- Include: autor, titlu, editură/revistă, loc publicării, an
- Minim 70% cărți/articole de specialitate, maxim 30% surse online
- Surse din ultimii 20 de ani preponderent, cu câteva clasice
- Ordonate alfabetic după numele autorului
- O sursă pe linie
- Fără numerotare
{f"Teme principale: {topic_keywords}" if topic_keywords else ""}

Generează DOAR bibliografia, câte o sursă pe linie:"""
