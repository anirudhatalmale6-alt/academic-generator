"""
Registry page — View, search, and manage generated documents.
"""

import streamlit as st
from pathlib import Path

from core.registry import DocumentRegistry


def render(app_dir: Path):
    st.title("Registru Documente")

    registry_path = app_dir / "registry.json"
    registry = DocumentRegistry(registry_path)

    # Stats
    st.metric("Total documente generate", registry.count)

    if registry.count == 0:
        st.info("Niciun document generat încă. Folosiți pagina Generator pentru a crea primul document.")
        return

    # Search and filter
    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("Căutare (cod sau titlu)", value="")
    with col2:
        type_filter = st.selectbox(
            "Filtru tip document",
            ["(Toate)"] + list({e["type"] for e in registry.list_all()}),
        )

    # Get results
    doc_type = type_filter if type_filter != "(Toate)" else ""
    results = registry.search(query=search_query, doc_type=doc_type)

    if not results:
        st.warning("Nu s-au găsit documente pentru criteriile selectate.")
        return

    # Display results
    for entry in results:
        with st.expander(f"{entry['code']} — {entry['title']}", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Tip:** {entry['type']}")
                st.write(f"**Limbă:** {entry['language']}")
                st.write(f"**Pagini:** {entry['pages']}")
                st.write(f"**Stil citare:** {entry['citation_style']}")
            with col2:
                st.write(f"**Data:** {entry['created_at'][:19]}")
                meta = entry.get("meta", {})
                if meta.get("university"):
                    st.write(f"**Universitate:** {meta['university']}")
                if meta.get("supervisor"):
                    st.write(f"**Coordonator:** {meta['supervisor']}")
                if meta.get("student"):
                    st.write(f"**Student:** {meta['student']}")

            # Download button
            output_path = Path(entry["output_path"])
            if output_path.exists():
                with open(output_path, "rb") as f:
                    st.download_button(
                        f"Descarcă {output_path.name}",
                        data=f.read(),
                        file_name=output_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_{entry['code']}",
                    )
            else:
                st.warning(f"Fișierul nu a fost găsit: {output_path}")

            # Delete button
            if st.button(f"Șterge din registru", key=f"del_{entry['code']}"):
                registry.remove(entry["code"])
                st.rerun()
