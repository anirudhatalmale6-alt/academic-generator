"""
Editor page — Load and modify an existing generated document.
"""

import re
import streamlit as st
from pathlib import Path
from docx import Document

from core.registry import DocumentRegistry
from core.ai_providers import generate_text, get_available_providers
from core.document_builder import AcademicDocBuilder
from core.citation_engine import get_style, find_citations, CITATION_PATTERN
from core.prompt_builder import build_system_prompt


def render(app_dir: Path):
    st.title("Editor Document")
    st.markdown("Încărcați un document existent și modificați secțiuni specifice folosind AI.")

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

    # ─── Section selection ─────────────────────────────────────────
    st.markdown("---")
    st.subheader("Modificare Secțiune")

    if not headings:
        return

    heading_options = [f"{h['indent']}{h['title']}" for h in headings]
    selected_heading_idx = st.selectbox(
        "Selectați secțiunea de modificat",
        range(len(headings)),
        format_func=lambda i: heading_options[i],
    )

    selected_heading = headings[selected_heading_idx]

    # Extract current section content
    start_idx = selected_heading["index"]
    end_idx = len(doc.paragraphs)
    for h in headings:
        if h["index"] > start_idx:
            end_idx = h["index"]
            break

    current_content = "\n\n".join(
        doc.paragraphs[i].text
        for i in range(start_idx + 1, end_idx)
        if doc.paragraphs[i].text.strip()
    )

    st.text_area(
        "Conținut curent",
        value=current_content[:2000] + ("..." if len(current_content) > 2000 else ""),
        height=200,
        disabled=True,
    )

    # ─── Modification instructions ─────────────────────────────────
    modification = st.text_area(
        "Instrucțiuni de modificare",
        height=150,
        help="Descrieți ce modificări doriți pentru această secțiune.",
        placeholder="Ex: Adaugă mai multe detalii despre metodologia cercetării...",
    )

    providers = get_available_providers()
    provider_list = list(providers.keys())

    st.warning(f"Secțiunea selectată pentru modificare: **{selected_heading['title']}**")

    if st.button("Aplică Modificarea", type="primary", disabled=not modification.strip()):
        if not provider_list:
            st.error("Niciun provider AI configurat!")
            return

        with st.spinner(f"Se regenerează secțiunea '{selected_heading['title']}'..."):
            prompt = f"""Ai mai jos conținutul actual al secțiunii '{selected_heading['title']}':

--- CONȚINUT ACTUAL ---
{current_content[:4000]}
--- SFÂRȘIT CONȚINUT ---

Instrucțiuni de modificare:
{modification}

Rescrie secțiunea aplicând modificările cerute. Păstrează stilul academic, lungimea similară,
și citările existente. Adaugă citări noi dacă este necesar, în format (Autor, An, p. X).
NU folosi markdown. Scrie proză academică continuă.

Scrie DOAR conținutul modificat:"""

            try:
                new_content, provider_used = generate_text(
                    prompt=prompt,
                    system_prompt=build_system_prompt(provider_list[0]),
                    provider_order=provider_list,
                    max_tokens=4096,
                )

                st.success(f"Secțiune regenerată cu {provider_used}")
                st.text_area("Conținut nou", value=new_content, height=300, disabled=True)

                # Rebuild document with modified section
                new_doc = Document(str(doc_path))

                # Replace section content
                # Remove old paragraphs (in reverse to preserve indices)
                for i in range(end_idx - 1, start_idx, -1):
                    p = new_doc.paragraphs[i]
                    p._element.getparent().remove(p._element)

                # Insert new content after the heading
                heading_element = new_doc.paragraphs[start_idx]._element
                parent = heading_element.getparent()

                for para_text in reversed(new_content.strip().split("\n\n")):
                    para_text = para_text.strip()
                    if not para_text:
                        continue
                    new_p = new_doc.add_paragraph(para_text)
                    # Move it after the heading
                    parent.remove(new_p._element)
                    heading_element.addnext(new_p._element)

                # Save as new version
                stem = doc_path.stem
                version_match = re.search(r'_v(\d+)$', stem)
                if version_match:
                    version = int(version_match.group(1)) + 1
                    new_stem = re.sub(r'_v\d+$', f'_v{version}', stem)
                else:
                    new_stem = f"{stem}_v2"

                new_path = doc_path.parent / f"{new_stem}.docx"
                new_doc.save(str(new_path))

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
