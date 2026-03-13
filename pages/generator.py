"""
Generator page — Main document generation form with all input fields.
All widgets are outside st.form() so mode changes (TOC, bibliography) trigger
immediate UI updates.
"""

import streamlit as st
from pathlib import Path
from datetime import datetime

from core.formatting import (
    LANGUAGES, DOCUMENT_TYPES, DEFAULT_CHAPTERS, DETAIL_MULTIPLIERS, TONE_OPTIONS,
)
from core.citation_engine import get_available_styles, load_custom_styles
from core.guide_reader import scan_guides_directory
from core.registry import DocumentRegistry
from core.pipeline import GenerationPipeline
from core.ai_providers import get_available_providers


def render(app_dir: Path):
    st.title("Generator de Documente Academice")

    # Initialize session state
    if "generating" not in st.session_state:
        st.session_state.generating = False
    if "generation_log" not in st.session_state:
        st.session_state.generation_log = []

    # Paths
    output_dir = app_dir / "outputs"
    guides_dir = app_dir / "ghiduri_academice"
    citation_dir = app_dir / "citation_styles"
    registry_path = app_dir / "registry.json"

    # Ensure directories exist
    output_dir.mkdir(exist_ok=True)
    guides_dir.mkdir(exist_ok=True)

    # ─── Sidebar: AI Provider Controls ─────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.subheader("Provideri AI")

    available_providers = get_available_providers()
    if available_providers:
        st.sidebar.success(f"{len(available_providers)} provider(i) activ(i)")
        for name in available_providers:
            st.sidebar.write(f"- {name.capitalize()}: {available_providers[name].model}")
    else:
        st.sidebar.warning("Niciun provider API configurat. Adăugați chei în fișierul .env")

    all_providers = ["claude", "openai", "gemini"]
    provider_order = st.sidebar.multiselect(
        "Ordinea providerilor (prioritate)",
        all_providers,
        default=[p for p in ["claude", "openai", "gemini"] if p in available_providers],
        help="Primul provider va fi încercat mai întâi. Dacă eșuează, se trece la următorul.",
    )

    # Warn about providers selected but not configured
    for p in provider_order:
        if p not in available_providers:
            st.sidebar.warning(f"⚠ {p.capitalize()}: Cheie API lipsă — va fi omis!")

    # ─── Document Identification ───────────────────────────────
    st.subheader("1. Identificare Document")
    col1, col2 = st.columns(2)

    with col1:
        code = st.text_input(
            "Cod document (identificator unic)",
            value="",
            help="Cod unic pentru identificare și denumirea fișierului",
        )
        title = st.text_input(
            "Titlu / Temă",
            value="",
            help="Titlul complet al lucrării",
        )
        doc_type = st.selectbox("Tip document", DOCUMENT_TYPES)

    with col2:
        language = st.selectbox("Limbă", LANGUAGES)
        page_count = st.number_input(
            "Număr pagini țintă",
            min_value=5, max_value=200, value=50,
        )
        domain = st.text_input(
            "Domeniu / Specializare",
            value="",
            help="Domeniul academic al lucrării",
        )

    # ─── Table of Contents / Structure ─────────────────────────
    st.subheader("2. Cuprins / Structură")

    toc_mode = st.radio(
        "Mod cuprins",
        ["Automat", "Automat din atașamente", "Manual", "Manual + din atașamente"],
        horizontal=True,
    )

    toc_manual = ""
    if toc_mode in ("Manual", "Manual + din atașamente"):
        default_chapters = DEFAULT_CHAPTERS.get(doc_type, DEFAULT_CHAPTERS["licență"])
        toc_manual = st.text_area(
            "Capitole (câte un capitol pe linie)",
            value="\n".join(default_chapters),
            height=200,
            help="Introduceți structura cuprinsului. Folosiți TAB pentru subcapitole.",
        )

    # detail_level uses Standard by default
    detail_level = "Standard"
    keywords = ""  # Will be set in Section 6

    # ─── Bibliography Settings ─────────────────────────────────
    st.subheader("3. Bibliografie")
    col1, col2, col3 = st.columns(3)

    with col1:
        min_sources = st.number_input(
            "Număr minim de surse",
            min_value=5, max_value=200, value=20,
        )
    with col2:
        # Load citation styles
        style_names = get_available_styles()
        custom_styles = load_custom_styles(citation_dir)
        all_style_names = style_names + [s for s in custom_styles if s not in style_names]
        citation_style = st.selectbox("Stil de citare", all_style_names)

    with col3:
        footnotes_per_page = st.number_input(
            "Note de subsol pe pagină (țintă)",
            min_value=0, max_value=8, value=2,
        )

    biblio_mode = st.radio(
        "Mod bibliografie",
        ["AI propune surse", "Manual", "Upload .bib"],
        horizontal=True,
    )

    biblio_manual = ""
    bib_file = None
    if biblio_mode == "Manual":
        biblio_manual = st.text_area(
            "Surse bibliografice (câte una pe linie)",
            height=150,
            help="Introduceți sursele exact așa cum doriți să apară în bibliografie.",
        )
    elif biblio_mode == "Upload .bib":
        bib_file = st.file_uploader("Încărcați fișier .bib", type=["bib"])

    # ─── Author & Academic Metadata ────────────────────────────
    st.subheader("4. Date Autor și Academice")
    st.caption("Aceste date apar pe pagina de copertă a documentului generat.")
    col1, col2 = st.columns(2)

    with col1:
        university = st.text_input("Universitate / Facultate", value="")
        supervisor = st.text_input("Profesor coordonator", value="")
    with col2:
        faculty = st.text_input("Facultatea", value="")
        student = st.text_input("Nume student / absolvent", value="")

    specialisation = st.text_input("Specializarea", value="")

    # ─── University Guides ─────────────────────────────────────
    st.subheader("5. Ghiduri Academice")

    guides_structure = scan_guides_directory(guides_dir)
    selected_guide_files = []

    if guides_structure:
        univ_names = list(guides_structure.keys())
        selected_univ = st.selectbox(
            "Universitate (din biblioteca locală)",
            ["(Niciuna)"] + univ_names,
        )

        if selected_univ != "(Niciuna)" and selected_univ in guides_structure:
            faculties = list(guides_structure[selected_univ].keys())
            selected_fac = st.selectbox("Facultate", ["(Toate)"] + faculties)

            if selected_fac == "(Toate)":
                all_guides = []
                for fac_guides in guides_structure[selected_univ].values():
                    all_guides.extend(fac_guides)
            else:
                all_guides = guides_structure[selected_univ].get(selected_fac, [])

            if all_guides:
                guide_names = [g.name for g in all_guides]
                selected = st.multiselect(
                    "Ghiduri selectate",
                    guide_names,
                    default=guide_names,
                )
                selected_guide_files = [g for g in all_guides if g.name in selected]
    else:
        st.info(
            f"Niciun ghid găsit în `{guides_dir.name}/`. "
            "Creați structura: `ghiduri_academice/Universitate/Facultate/ghid.pdf`"
        )

    # ─── Additional Context ───────────────────────────────────
    st.subheader("6. Context Suplimentar")

    keywords = st.text_input(
        "Cuvinte cheie / teme principale",
        value="",
        help="Teme și subiecte pe care AI-ul să le acopere în conținut",
    )
    other_details = st.text_area(
        "Alte detalii / cerințe speciale",
        value="",
        height=100,
        help="Instrucțiuni suplimentare injectate în promptul AI",
    )
    tone = st.selectbox("Ton", TONE_OPTIONS)

    # ─── File Uploads ──────────────────────────────────────────
    st.subheader("7. Încărcare Fișiere")

    uploaded_files = st.file_uploader(
        "Ghiduri, documente sursă, date (PDF, DOCX, TXT, CSV, XLSX)",
        type=["pdf", "docx", "txt", "csv", "xlsx", "md"],
        accept_multiple_files=True,
    )

    author_style_file = st.file_uploader(
        "Manifest stil autor (ex: AI_Uman.docx)",
        type=["docx", "txt", "md"],
        help="Preferințe de scriere injectate în prompt",
    )

    # ─── Submit ───────────────────────────────────────────────
    st.markdown("---")
    submitted = st.button(
        "Generează Document",
        type="primary",
        use_container_width=True,
    )

    # ─── Generation Process ───────────────────────────────────────
    if submitted:
        # Validation
        if not code.strip():
            st.error("Codul documentului este obligatoriu!")
            return
        if not title.strip():
            st.error("Titlul documentului este obligatoriu!")
            return
        if not provider_order:
            st.error("Selectați cel puțin un provider AI!")
            return

        # Save uploaded files locally
        upload_dir = output_dir / code / "attachments"
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved_uploads = []
        for uf in (uploaded_files or []):
            file_path = upload_dir / uf.name
            file_path.write_bytes(uf.read())
            saved_uploads.append(file_path)

        if author_style_file:
            style_path = upload_dir / author_style_file.name
            style_path.write_bytes(author_style_file.read())
            saved_uploads.append(style_path)

        # Save .bib file if uploaded
        bib_path = None
        if bib_file:
            bib_path = upload_dir / bib_file.name
            bib_path.write_bytes(bib_file.read())

        # Progress display
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_callback(message: str, progress: float):
            progress_bar.progress(min(progress, 1.0))
            status_text.info(message)

        # Run pipeline
        registry = DocumentRegistry(registry_path)
        pipeline = GenerationPipeline(
            output_dir=output_dir,
            registry=registry,
            progress_callback=progress_callback,
        )

        try:
            output_path = pipeline.generate_document(
                code=code.strip(),
                title=title.strip(),
                doc_type=doc_type,
                language=language,
                page_count=page_count,
                toc_mode=toc_mode,
                toc_manual=toc_manual,
                citation_style_name=citation_style,
                footnotes_per_page=footnotes_per_page,
                min_sources=min_sources,
                biblio_mode=biblio_mode,
                biblio_manual=biblio_manual,
                bib_file_path=bib_path,
                provider_order=provider_order,
                university=university,
                faculty=faculty,
                specialisation=specialisation,
                supervisor=supervisor,
                student=student,
                detail_level=detail_level,
                tone=tone,
                keywords=keywords,
                other_details=other_details,
                guide_files=selected_guide_files,
                uploaded_files=saved_uploads,
            )

            st.success(f"Document generat cu succes: {output_path.name}")

            # Download button
            with open(output_path, "rb") as f:
                st.download_button(
                    label="Descarcă Documentul (.docx)",
                    data=f.read(),
                    file_name=output_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                )

        except Exception as e:
            st.error(f"Eroare la generare: {e}")
            import traceback
            st.expander("Detalii eroare").code(traceback.format_exc())
