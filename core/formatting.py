"""Document formatting constants for Romanian academic standards."""

from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Font settings
FONT_BODY = "Times New Roman"
FONT_SIZE_BODY = Pt(12)
FONT_SIZE_FOOTNOTE = Pt(10)
FONT_SIZE_H1 = Pt(16)
FONT_SIZE_H2 = Pt(14)
FONT_SIZE_H3 = Pt(12)
FONT_SIZE_COVER_TITLE = Pt(20)
FONT_SIZE_COVER_SUBTITLE = Pt(14)
FONT_COLOR = RGBColor(0, 0, 0)

# Spacing (in twips: 1 line = 240 twips)
LINE_SPACING_BODY = 1.5
LINE_SPACING_FOOTNOTE = 1.0
LINE_SPACING_BIBLIO = 1.0
SPACE_AFTER_PARAGRAPH = Pt(0)

# Indentation
FIRST_LINE_INDENT = Cm(1.25)
HANGING_INDENT_BIBLIO = Cm(1.25)

# Margins
MARGIN_LEFT = Cm(3)    # Binding margin
MARGIN_RIGHT = Cm(2)
MARGIN_TOP = Cm(2.5)
MARGIN_BOTTOM = Cm(2.5)

# Alignment
ALIGN_BODY = WD_ALIGN_PARAGRAPH.JUSTIFY
ALIGN_CENTER = WD_ALIGN_PARAGRAPH.CENTER
ALIGN_LEFT = WD_ALIGN_PARAGRAPH.LEFT

# Heading styles
HEADING_STYLES = {
    1: {"size": FONT_SIZE_H1, "bold": True, "italic": False, "alignment": ALIGN_CENTER},
    2: {"size": FONT_SIZE_H2, "bold": True, "italic": False, "alignment": ALIGN_LEFT},
    3: {"size": FONT_SIZE_H3, "bold": True, "italic": False, "alignment": ALIGN_LEFT},
}

# Supported languages
LANGUAGES = [
    "Română", "Engleză", "Franceză", "Spaniolă", "Germană", "Maghiară"
]

# Document types
DOCUMENT_TYPES = [
    "licență", "disertație", "doctorat", "grad didactic", "diplomă"
]

# Default chapter templates per document type
DEFAULT_CHAPTERS = {
    "licență": [
        "Introducere",
        "Capitolul I – Cadrul teoretic",
        "Capitolul II – Analiza / Studiul aplicativ",
        "Capitolul III – Concluzii și propuneri",
        "Bibliografie",
    ],
    "disertație": [
        "Introducere",
        "Capitolul I – Cadrul teoretic și stadiul cercetării",
        "Capitolul II – Metodologia cercetării",
        "Capitolul III – Analiza datelor și interpretare",
        "Capitolul IV – Concluzii și direcții de cercetare",
        "Bibliografie",
    ],
    "doctorat": [
        "Introducere",
        "Capitolul I – Stadiul actual al cunoașterii",
        "Capitolul II – Fundamentare teoretică",
        "Capitolul III – Metodologia cercetării",
        "Capitolul IV – Rezultate și discuții",
        "Capitolul V – Concluzii și contribuții originale",
        "Bibliografie",
    ],
    "grad didactic": [
        "Argument",
        "Capitolul I – Cadrul teoretic",
        "Capitolul II – Cercetarea aplicativă",
        "Capitolul III – Rezultate și interpretare",
        "Concluzii",
        "Bibliografie",
    ],
    "diplomă": [
        "Introducere",
        "Capitolul I – Fundamentare teoretică",
        "Capitolul II – Proiectare și implementare",
        "Capitolul III – Testare și evaluare",
        "Concluzii",
        "Bibliografie",
    ],
}

# Detail level multipliers for section length
DETAIL_MULTIPLIERS = {
    "Sumar": 0.6,
    "Standard": 1.0,
    "Detaliat": 1.5,
}

# Tone options
TONE_OPTIONS = [
    "Formal academic",
    "Neutru",
    "Tehnic",
    "Literar",
]
