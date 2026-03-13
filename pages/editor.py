"""
Editor page — Load and modify an existing document using free-text instructions.
The AI applies all changes in a single pass based on the user's description.
"""

import re
import streamlit as st
from pathlib import Path
from docx import Document

from core.registry import DocumentRegistry
from core.ai_providers import generate_text, get_available_providers
from core.document_builder import AcademicDocBuilder
from core.prompt_builder import build_system_prompt
from core.guide_reader import extract_text as extract_guide_text


def render(app_dir: Path):
    st.title("Editor Document")
    st.markdown("Încărcați un document și descrieți toate modificările dorite. AI-ul le va aplica într-o singură trecere.")

    registry_path = app_dir / "registry.json"
    output_dir = app_dir / "outputs"
    registry = DocumentRegistry(registry_path)

    # ─── Source selection ──────────────────────────────────────────
    source = st.radio("Sursă document", ["Din registru", "Încărcare fișier"], horizontal=True)

    doc_path = None
    doc_code = ""

    if source == "Din registru":
        entries = registry.list_all()
        if not entries:
            st.info("Registrul este gol. Generați un document mai întâi.")
            return

        options = {f"{e['code']} — {e['title']}": e for e in entries}
        selected = st.selectbox("Selectați documentul", list(options.keys()))
        if selected:
            entry = options[selected]
            doc_path = Path(entry["output_path"])
            doc_code = entry["code"]
            if not doc_path.exists():
                st.error(f"Fișierul nu a fost găsit: {doc_path}")
                return
    else:
        uploaded = st.file_uploader("Încărcați document .docx", type=["docx"])
        if uploaded:
            tmp_path = output_dir / "_editor_temp" / uploaded.name
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(uploaded.read())
            doc_path = tmp_path
            doc_code = tmp_path.stem

    if doc_path is None:
        return

    # ─── Load and display document structure ───────────────────────
    try:
        doc = Document(str(doc_path))
    except Exception as e:
        st.error(f"Eroare la deschiderea documentului: {e}")
        return

    st.markdown("---")
    st.subheader("Structura documentului")

    # Extract headings
    headings = []
    for i, para in enumerate(doc.paragraphs):
        if para.style.name.startswith("Heading"):
            level = int(para.style.name.split()[-1])
            headings.append({
                "index": i,
                "level": level,
                "title": para.text,
                "indent": "  " * (level - 1),
            })

    if headings:
        for h in headings:
            st.markdown(f"{h['indent']}{h['title']}")
    else:
        st.info("Nu s-au găsit titluri de secțiuni în document.")

    # ─── Modification instructions ─────────────────────────────────
    st.markdown("---")
    st.subheader("Instrucțiuni de Modificare")

    modification = st.text_area(
        "Descrieți toate modificările dorite",
        height=200,
        help="Descrieți liber ce modificări doriți. Puteți menționa secțiuni specifice, cereri de adăugare/eliminare conținut, etc.",
        placeholder="Ex: Rescrie secțiunea Concluzii cu accent pe rezultatele practice. "
                    "Adaugă mai multe detalii în Introducere despre contextul economic actual. "
                    "Corectează greșelile gramaticale din tot documentul.",
    )

    # ─── Reference file uploads ────────────────────────────────────
    ref_files = st.file_uploader(
        "Fișiere de referință (opțional)",
        type=["pdf", "docx", "txt", "csv", "xlsx", "md"],
        accept_multiple_files=True,
        help="Fișiere pe care AI-ul ar trebui să le ia în considerare la modificare.",
    )

    providers = get_available_providers()
    provider_list = list(providers.keys())

    if st.button("Aplică Modificările", type="primary", disabled=not modification.strip(), use_container_width=True):
        if not provider_list:
            st.error("Niciun provider AI configurat!")
            return

        # Extract full document content
        full_content = ""
        for para in doc.paragraphs:
            if para.style.name.startswith("Heading"):
                level = int(para.style.name.split()[-1])
                full_content += f"\n{'#' * level} {para.text}\n\n"
            elif para.text.strip():
                full_content += f"{para.text}\n\n"

        # Truncate if too long
        max_content = 12000
        if len(full_content) > max_content:
            full_content = full_content[:max_content] + "\n\n[... conținut trunchiat ...]"

        # Extract reference file content
        ref_context = ""
        saved_refs = []
        if ref_files:
            ref_dir = output_dir / "_editor_temp" / "refs"
            ref_dir.mkdir(parents=True, exist_ok=True)
            for rf in ref_files:
                ref_path = ref_dir / rf.name
                ref_path.write_bytes(rf.read())
                saved_refs.append(ref_path)
                text = extract_guide_text(ref_path)
                if text:
                    ref_context += f"\n--- Fișier referință: {rf.name} ---\n{text[:3000]}\n"

        with st.spinner("Se aplică modificările..."):
            prompt = f"""Ai mai jos conținutul complet al unui document academic:

--- DOCUMENT ORIGINAL ---
{full_content}
--- SFÂRȘIT DOCUMENT ---
{f'''
--- FIȘIERE DE REFERINȚĂ ---
{ref_context}
--- SFÂRȘIT REFERINȚE ---
''' if ref_context else ''}
Instrucțiuni de modificare de la utilizator:
{modification}

IMPORTANT:
- Aplică TOATE modificările cerute de utilizator
- Păstrează structura documentului (titluri cu # pentru H1, ## pentru H2, ### pentru H3)
- Păstrează stilul academic și tonul formal
- Păstrează citările existente în format (Autor, An) sau (Autor, An, p. X)
- NU folosi markdown bold/italic (*text*)
- Scrie proză academică continuă, fără liste cu bullets
- Returnează ÎNTREGUL document modificat, nu doar secțiunile schimbate

Scrie documentul modificat complet:"""

            try:
                new_content, provider_used = generate_text(
                    prompt=prompt,
                    system_prompt=build_system_prompt(provider_list[0]),
                    provider_order=provider_list,
                    max_tokens=4096,
                )

                st.success(f"Modificări aplicate cu {provider_used}")

                # Show preview of changes
                with st.expander("Previzualizare conținut modificat", expanded=True):
                    st.text_area("Conținut nou", value=new_content, height=400, disabled=True)

                # Rebuild document
                builder = AcademicDocBuilder()

                # Parse AI output and rebuild sections
                lines = new_content.strip().split("\n")
                current_para = []

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        if current_para:
                            text = " ".join(current_para)
                            text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
                            p = builder.doc.add_paragraph(text)
                            builder._apply_body_format(p)
                            current_para = []
                        continue

                    heading_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
                    if heading_match:
                        if current_para:
                            text = " ".join(current_para)
                            text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
                            p = builder.doc.add_paragraph(text)
                            builder._apply_body_format(p)
                            current_para = []

                        level = len(heading_match.group(1))
                        h_text = heading_match.group(2).strip()
                        builder.doc.add_heading(h_text, level=min(level, 3))
                    else:
                        stripped = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', stripped)
                        stripped = re.sub(r'^[-•]\s+', '', stripped)
                        current_para.append(stripped)

                if current_para:
                    text = " ".join(current_para)
                    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
                    p = builder.doc.add_paragraph(text)
                    builder._apply_body_format(p)

                # Save as new version
                stem = doc_path.stem
                version_match = re.search(r'_v(\d+)$', stem)
                if version_match:
                    version = int(version_match.group(1)) + 1
                    new_stem = re.sub(r'_v\d+$', f'_v{version}', stem)
                else:
                    new_stem = f"{stem}_v2"

                new_path = doc_path.parent / f"{new_stem}.docx"
                builder.save(new_path)

                st.success(f"Document salvat: {new_path.name}")
                with open(new_path, "rb") as f:
                    st.download_button(
                        "Descarcă documentul modificat",
                        data=f.read(),
                        file_name=new_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )

            except Exception as e:
                st.error(f"Eroare: {e}")
                import traceback
                st.expander("Detalii eroare").code(traceback.format_exc())
