"""
Main document generation pipeline.
Orchestrates: AI generation → citation injection → DOCX assembly → registry.
"""

import re
import logging
from pathlib import Path
from typing import Optional, Callable

from core.ai_providers import generate_text, AIProviderError
from core.document_builder import AcademicDocBuilder
from core.citation_engine import find_citations, get_style, CITATION_PATTERN, FootnoteFormatter
from core.bibliography import validate_bibliography, parse_bib_file, search_crossref
from core.prompt_builder import (
    build_system_prompt, build_section_prompt, build_abstract_prompt,
    build_toc_prompt, build_bibliography_prompt,
)
from core.guide_reader import extract_text as extract_guide_text, extract_formatting_rules
from core.registry import DocumentRegistry

logger = logging.getLogger(__name__)


def parse_toc_input(toc_text: str) -> list[dict]:
    """Parse user-provided TOC text into structured sections.

    Returns list of dicts with keys: title, level
    """
    sections = []
    for line in toc_text.strip().split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue

        # Determine level from indentation
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if indent == 0 or stripped.startswith("#"):
            level = 1
        elif indent <= 4 or stripped.startswith("##"):
            level = 2
        else:
            level = 3

        # Clean heading markers
        title = re.sub(r'^#{1,3}\s*', '', stripped).strip()
        if title:
            sections.append({"title": title, "level": level})

    return sections


def parse_ai_toc(ai_output: str) -> list[dict]:
    """Parse AI-generated TOC into structured sections."""
    sections = []
    for line in ai_output.strip().split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Remove numbering like "1.", "1.1.", "I.", etc.
        title = re.sub(r'^[\d.]+\s*[-–]?\s*', '', stripped)
        title = re.sub(r'^[IVXLC]+\.\s*[-–]?\s*', '', title)
        title = title.strip()

        if not title:
            continue

        level = 2 if indent > 0 or re.match(r'^\d+\.\d+', stripped) else 1
        sections.append({"title": title, "level": level})

    return sections


class GenerationPipeline:
    """Orchestrates the full document generation process."""

    def __init__(
        self,
        output_dir: Path,
        registry: DocumentRegistry,
        progress_callback: Callable[[str, float], None] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.registry = registry
        self.progress_callback = progress_callback or (lambda msg, pct: None)

    def _report(self, message: str, progress: float):
        self.progress_callback(message, progress)

    def generate_document(
        self,
        code: str,
        title: str,
        doc_type: str,
        language: str,
        page_count: int,
        toc_mode: str,
        toc_manual: str,
        citation_style_name: str,
        footnotes_per_page: int,
        min_sources: int,
        biblio_mode: str,
        biblio_manual: str,
        bib_file_path: Optional[Path],
        provider_order: list[str],
        university: str,
        faculty: str,
        specialisation: str,
        supervisor: str,
        student: str,
        detail_level: str,
        tone: str,
        keywords: str,
        other_details: str,
        guide_files: list[Path] | None = None,
        uploaded_files: list[Path] | None = None,
    ) -> Path:
        """Run the full generation pipeline. Returns path to the generated DOCX."""

        total_steps = 6  # TOC, bibliography, sections, abstract, assembly, save
        step = 0

        # ─── Step 1: Determine TOC structure ──────────────────────────
        step += 1
        self._report("Determinare structură cuprins...", step / total_steps)

        if toc_mode == "Manual" and toc_manual.strip():
            sections = parse_toc_input(toc_manual)
        elif toc_mode == "Manual + din atașamente":
            # Priority: manual text first, then try to extract from uploads
            if toc_manual.strip():
                sections = parse_toc_input(toc_manual)
            elif uploaded_files:
                extracted = self._extract_toc_from_files(uploaded_files)
                if extracted:
                    sections = extracted
                else:
                    sections = self._auto_generate_toc(title, doc_type, language, page_count, provider_order)
            else:
                sections = self._auto_generate_toc(title, doc_type, language, page_count, provider_order)
        elif toc_mode == "Automat din atașamente" and uploaded_files:
            extracted = self._extract_toc_from_files(uploaded_files)
            if extracted:
                sections = extracted
            else:
                sections = self._auto_generate_toc(title, doc_type, language, page_count, provider_order)
        elif toc_mode == "Automat":
            sections = self._auto_generate_toc(title, doc_type, language, page_count, provider_order)
        else:
            # Fallback to defaults
            from core.formatting import DEFAULT_CHAPTERS
            default = DEFAULT_CHAPTERS.get(doc_type, DEFAULT_CHAPTERS["licență"])
            sections = [{"title": ch, "level": 1} for ch in default]

        # Ensure bibliography section exists
        has_biblio = any(
            "bibliografi" in s["title"].lower() or "referinț" in s["title"].lower()
            for s in sections
        )
        if not has_biblio:
            sections.append({"title": "Bibliografie", "level": 1})

        # ─── Step 2: Generate bibliography ────────────────────────────
        step += 1
        self._report("Generare bibliografie...", step / total_steps)

        biblio_entries = self._generate_bibliography(
            title, doc_type, language, min_sources, citation_style_name,
            biblio_mode, biblio_manual, bib_file_path, keywords, provider_order,
        )

        # ─── Step 3: Read guides ─────────────────────────────────────
        guides_text = ""
        formatting_rules = {}
        all_guide_files = list(guide_files or []) + list(uploaded_files or [])
        for gf in all_guide_files:
            text = extract_guide_text(gf)
            if text:
                guides_text += f"\n\n--- {Path(gf).name} ---\n{text}"
                rules = extract_formatting_rules(text)
                formatting_rules.update(rules)

        # ─── Step 4: Generate content sections ────────────────────────
        step += 1
        content_sections = []
        non_biblio_sections = [s for s in sections if "bibliografi" not in s["title"].lower()]
        total_content = len(non_biblio_sections)

        system_prompt = build_system_prompt(provider_order[0] if provider_order else "claude", language, tone)

        import time as _time

        for i, section in enumerate(non_biblio_sections):
            # Pause between sections to avoid API rate limits (8K tokens/min on free tiers)
            if i > 0:
                self._report(f"Pauză scurtă pentru limita API...", step / total_steps)
                _time.sleep(10)

            section_progress = step / total_steps + (i / total_content) * (1 / total_steps)
            self._report(f"Generare secțiune: {section['title']}...", section_progress)

            prompt = build_section_prompt(
                section_name=section["title"],
                title=title,
                doc_type=doc_type,
                language=language,
                total_pages=page_count,
                total_sections=total_content,
                detail_level=detail_level,
                citation_style_name=citation_style_name,
                footnotes_per_page=footnotes_per_page,
                keywords=keywords,
                other_details=other_details,
                guides_text=guides_text,
                formatting_rules=formatting_rules if formatting_rules else None,
                bibliography_entries=biblio_entries,
                previous_sections=[s["title"] for s in content_sections],
            )

            # Calculate token budget: ~450 tokens/page for Romanian text,
            # distributed across sections, with buffer to avoid mid-sentence cuts.
            from core.prompt_builder import calculate_section_length
            sec_length = calculate_section_length(
                section["title"], page_count, total_content, detail_level,
            )
            # Tokens = estimated_pages * 450 tokens/page * 1.3 safety buffer
            # Minimum 600 (enough for 2 good paragraphs), maximum 4096
            section_tokens = max(600, min(4096, int(sec_length["estimated_pages"] * 450 * 1.3)))

            try:
                text, provider_used = generate_text(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    provider_order=provider_order,
                    max_tokens=section_tokens,
                    temperature=0.7,
                )
            except AIProviderError as e:
                text = f"[Eroare la generare: {e}]"
                provider_used = "none"

            content_sections.append({
                "title": section["title"],
                "level": section["level"],
                "content": text,
                "provider": provider_used,
            })

        # ─── Step 5: Generate abstract ────────────────────────────────
        step += 1
        self._report("Generare rezumat...", step / total_steps)

        abstract_prompt = build_abstract_prompt(
            title, doc_type, language,
            [s["title"] for s in non_biblio_sections],
        )
        try:
            abstract_text, _ = generate_text(
                prompt=abstract_prompt,
                provider_order=provider_order,
                max_tokens=1024,
            )
        except AIProviderError:
            abstract_text = "[Rezumatul nu a putut fi generat automat.]"

        # ─── Step 6: Assemble DOCX ───────────────────────────────────
        step += 1
        self._report("Asamblare document Word...", step / total_steps)

        builder = AcademicDocBuilder()
        citation_style = get_style(citation_style_name)

        # Determine citation mode: footnote (AR/Chicago) vs inline (APA)
        use_footnotes = citation_style.citation_mode == "footnote"
        logger.info(f"Citation style: {citation_style.name}, mode: {citation_style.citation_mode}")

        # Create bibliography-aware footnote formatter (only needed for footnote mode)
        fn_formatter = FootnoteFormatter(biblio_entries, citation_style) if use_footnotes else None

        # Cover page
        import datetime
        builder.add_cover_page(
            title=title,
            doc_type=doc_type,
            university=university,
            faculty=faculty,
            specialisation=specialisation,
            supervisor=supervisor,
            student=student,
            year=str(datetime.datetime.now().year),
        )

        # Abstract
        builder.add_abstract(abstract_text)

        # TOC with field code (auto-updates on open via w:updateFields)
        builder.add_toc()

        # Page numbers (from this section onward)
        builder.add_page_numbers()

        # Content sections
        for section in content_sections:
            # Add heading and track it
            builder.doc.add_heading(section["title"], level=section["level"])
            builder.track_heading(section["title"], section["level"])

            # Process content paragraph by paragraph
            content = section["content"]
            # Remove duplicate heading if AI repeated it
            content = re.sub(
                r'^#{1,3}\s*' + re.escape(section["title"]) + r'\s*\n',
                '', content, count=1
            )

            paragraphs = content.strip().split("\n\n")
            for para_text in paragraphs:
                para_text = para_text.strip()
                if not para_text:
                    continue

                # Check for sub-headings
                heading_match = re.match(r'^(#{1,3})\s+(.+)$', para_text)
                if heading_match:
                    level = min(len(heading_match.group(1)), 3)
                    h_title = heading_match.group(2).strip()
                    builder.doc.add_heading(h_title, level=level)
                    builder.track_heading(h_title, level)
                    continue

                # Clean markdown — strip all asterisk formatting
                para_text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', para_text)
                para_text = re.sub(r'^[-•]\s+', '', para_text, flags=re.MULTILINE)
                para_text = " ".join(para_text.split("\n"))

                # Find citations
                citations = find_citations(para_text)

                if use_footnotes:
                    # ── FOOTNOTE MODE (AR / Chicago) ──────────────────
                    # Remove citation markers from text → clean paragraph
                    clean_text = CITATION_PATTERN.sub('', para_text).strip()
                    # Also strip any remaining parenthetical citations
                    clean_text = re.sub(
                        r'\(\s*[A-ZÀ-Ž][a-zà-ž]+(?:[-\s][A-ZÀ-Ž]?[a-zà-ž]*)*.{0,30}?\d{4}.{0,10}?\)',
                        '', clean_text,
                    )
                    clean_text = re.sub(r'\s{2,}', ' ', clean_text).strip()

                    if not clean_text:
                        continue

                    p = builder.doc.add_paragraph(clean_text)
                    builder._apply_body_format(p)

                    # One footnote per paragraph with exactly one source
                    if citations and fn_formatter:
                        fn_text = fn_formatter.format(
                            author=citations[0]["author"],
                            year=citations[0]["year"],
                            pages=citations[0]["pages"],
                        )
                        builder.add_footnote(p, fn_text)
                else:
                    # ── INLINE MODE (APA) ────────────────────────────
                    # Keep citations in text, reformat them according to style.
                    # NO Word footnotes created.
                    formatted_text = para_text

                    # Replace citations in reverse order to preserve positions
                    for cit in reversed(citations):
                        inline_ref = citation_style.format_inline(
                            author=cit["author"],
                            year=cit["year"],
                            pages=cit["pages"],
                        )
                        formatted_text = (
                            formatted_text[:cit["start"]]
                            + inline_ref
                            + formatted_text[cit["end"]:]
                        )

                    # APA: clean up broken citations (missing closing paren, etc.)
                    formatted_text = re.sub(
                        r'\(([A-ZÀ-Ž][a-zà-ž]+),\s*(\d{4})(?:\s*$)',
                        r'(\1, \2)',
                        formatted_text,
                    )

                    formatted_text = re.sub(r'\s{2,}', ' ', formatted_text).strip()

                    if not formatted_text:
                        continue

                    p = builder.doc.add_paragraph(formatted_text)
                    builder._apply_body_format(p)

        # Bibliography — strip markdown asterisks from entries
        clean_biblio = [re.sub(r'\*+([^*]+)\*+', r'\1', e) for e in biblio_entries]
        # Use "Referințe bibliografice" for inline styles, "Bibliografie" for footnote styles
        biblio_title = "Bibliografie" if use_footnotes else "Referințe bibliografice"
        builder.add_bibliography(clean_biblio, title=biblio_title)

        # Save
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '_')
        filename = f"{code}_{safe_title}.docx"
        doc_dir = self.output_dir / code
        output_path = doc_dir / filename
        builder.save(output_path)

        # Register
        self.registry.add(
            code=code,
            title=title,
            doc_type=doc_type,
            language=language,
            pages=page_count,
            citation_style=citation_style_name,
            output_path=str(output_path),
            metadata={
                "university": university,
                "faculty": faculty,
                "supervisor": supervisor,
                "student": student,
                "min_sources": min_sources,
                "biblio_mode": biblio_mode,
                "detail_level": detail_level,
                "tone": tone,
            },
        )

        self._report("Document generat cu succes!", 1.0)
        return output_path

    def _auto_generate_toc(self, title, doc_type, language, page_count, provider_order):
        """Generate TOC structure via AI."""
        prompt = build_toc_prompt(title, doc_type, language, page_count)
        try:
            text, _ = generate_text(prompt=prompt, provider_order=provider_order, max_tokens=1024)
            sections = parse_ai_toc(text)
            if sections:
                return sections
        except AIProviderError:
            pass

        # Fallback to defaults
        from core.formatting import DEFAULT_CHAPTERS
        default = DEFAULT_CHAPTERS.get(doc_type, DEFAULT_CHAPTERS["licență"])
        return [{"title": ch, "level": 1} for ch in default]

    def _extract_toc_from_files(self, files: list[Path]) -> list[dict]:
        """Extract TOC/chapter structure from uploaded files.

        Looks for chapter-like headings (Capitolul, Introducere, Concluzii, etc.)
        line by line, rather than relying on finding a 'Cuprins' keyword.
        """
        chapter_pattern = re.compile(
            r'^\s*(?:'
            r'(?:Capitolul|Capitol)\s+[IVXLC\d]+[\s.–\-:]+.+'  # Capitolul I — ...
            r'|Introducere.*'
            r'|Concluzi[ie].*'
            r'|Bibliografi[ea].*'
            r'|Rezumat.*'
            r'|Abstract.*'
            r'|\d+\.\s+.+'  # 1. Title
            r'|\d+\.\d+\.?\s+.+'  # 1.1 Subtitle
            r')',
            re.IGNORECASE,
        )

        for f in files:
            text = extract_guide_text(f)
            if not text:
                continue

            sections = []
            for line in text.split("\n"):
                line = line.rstrip()
                if not line.strip():
                    continue
                if chapter_pattern.match(line.strip()):
                    stripped = line.strip()
                    # Determine level
                    if re.match(r'^\d+\.\d+', stripped):
                        level = 2
                    elif re.match(r'^\t', line) or line.startswith("    "):
                        level = 2
                    else:
                        level = 1
                    # Clean title
                    title = re.sub(r'^\d+[\.\)]\s*', '', stripped)
                    title = title.strip()
                    if title and len(title) > 3:
                        sections.append({"title": title, "level": level})

            # Require at least 3 sections for a valid TOC extraction
            # (avoids false positives from guide/formatting files)
            if len(sections) >= 3:
                return sections

        return []

    def _generate_bibliography(
        self, title, doc_type, language, min_sources, citation_style_name,
        biblio_mode, biblio_manual, bib_file_path, keywords, provider_order,
    ) -> list[str]:
        """Generate or load bibliography entries."""

        if biblio_mode == "Manual" and biblio_manual.strip():
            entries = [e.strip() for e in biblio_manual.strip().split("\n") if e.strip()]
            return entries

        if biblio_mode == "Upload .bib" and bib_file_path:
            return parse_bib_file(bib_file_path)

        # AI-generated bibliography
        prompt = build_bibliography_prompt(
            title, doc_type, language, min_sources, citation_style_name, keywords,
        )
        try:
            text, _ = generate_text(prompt=prompt, provider_order=provider_order, max_tokens=4096)
            entries = [e.strip() for e in text.strip().split("\n") if e.strip() and len(e.strip()) > 20]

            # Try to supplement with Crossref if we don't have enough
            if len(entries) < min_sources:
                crossref_entries = search_crossref(f"{title} {keywords}", rows=min_sources - len(entries))
                entries.extend(crossref_entries)

            return entries[:max(min_sources, len(entries))]
        except AIProviderError:
            # Last resort: Crossref only
            return search_crossref(f"{title} {keywords}", rows=min_sources)
