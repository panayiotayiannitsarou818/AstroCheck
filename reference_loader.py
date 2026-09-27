import io
from pathlib import Path

import streamlit as st
from docx import Document

REFERENCE_DIR = Path(__file__).resolve().parent / "references"
DEFAULT_INSTRUCTIONS = REFERENCE_DIR / "Odigies_v5.docx"
DEFAULT_STYLE = REFERENCE_DIR / "Elena_style_guide_v2.docx"
ROOT_INSTRUCTIONS = Path(__file__).resolve().parent / "Odigies_v5.docx"
ROOT_STYLE = Path(__file__).resolve().parent / "Elena_style_guide_v2.docx"


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_NOTE_RELTYPES = ("/footnotes", "/endnotes")


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _paragraph_text(p) -> str:
    """Κείμενο μιας παραγράφου, ΧΩΡΙΣ τα πλαίσια κειμένου που περιέχει
    (αυτά διαβάζονται χωριστά, αμέσως μετά) και χωρίς διαγραμμένο κείμενο
    παρακολούθησης αλλαγών. Περιλαμβάνει όμως κείμενο που ΠΡΟΣΤΕΘΗΚΕ με
    παρακολούθηση αλλαγών, υπερσυνδέσμους και πεδία περιεχομένου."""
    parts = []

    def walk(node):
        for child in node:
            name = _local(child.tag)
            if name in ("txbxContent", "del", "delText", "instrText") or child.tag == _MC_FALLBACK:
                continue
            if name == "t":
                parts.append(child.text or "")
            elif name == "tab":
                parts.append("\t")
            elif name in ("br", "cr"):
                parts.append("\n")
            else:
                walk(child)

    walk(p)
    return "".join(parts).strip()


def _text_boxes(p):
    """Πλαίσια κειμένου μέσα σε μια παράγραφο. Το Word αποθηκεύει κάθε πλαίσιο
    δύο φορές (σύγχρονη μορφή και «Fallback» για παλιές εκδόσεις)· κρατάμε
    μόνο τη μία, ώστε το κείμενο να μη διπλασιάζεται."""
    for box in p.iter(_W + "txbxContent"):
        ancestor = box.getparent()
        nested = False
        while ancestor is not None and ancestor is not p:
            if ancestor.tag == _MC_FALLBACK or _local(ancestor.tag) == "txbxContent":
                nested = True
                break
            ancestor = ancestor.getparent()
        if not nested:
            yield box


def _block_lines(container) -> list[str]:
    """Γραμμές κειμένου ενός «σώματος» (κυρίως έγγραφο, κεφαλίδα, υποσέλιδο,
    υποσημείωση, πλαίσιο κειμένου, κελί), με τη σειρά του εγγράφου."""
    lines = []
    for child in container:
        name = _local(child.tag)
        if name == "p":
            text = _paragraph_text(child)
            if text:
                lines.append(text)
            for box in _text_boxes(child):
                lines.extend(_block_lines(box))
        elif name == "tbl":
            for row in child.iter(_W + "tr"):
                if row.getparent() is not child:
                    continue  # γραμμή εμφωλευμένου πίνακα -- διαβάζεται παρακάτω
                cells = []
                for cell in row.findall(_W + "tc"):
                    # Όπως πριν: οι παράγραφοι ενός κελιού χωρίζονται με αλλαγή
                    # γραμμής (π.χ. οι γραμμές του πλαισίου σύνοψης). Εμφωλευμένος
                    # πίνακας ή πλαίσιο μέσα στο κελί μένει μέσα στο ίδιο κελί.
                    t = "\n".join(_block_lines(cell)).strip()
                    if not cells or cells[-1] != t:  # συγχωνευμένα κελιά επαναλαμβάνονται
                        cells.append(t)
                line = " | ".join(cells)
                if line.strip(" |"):
                    lines.append(line)
        elif name == "sdt":
            content = child.find(_W + "sdtContent")
            if content is not None:
                lines.extend(_block_lines(content))
        elif name in ("customXml", "smartTag", "ins"):
            lines.extend(_block_lines(child))
    return lines


def docx_text(source) -> str:
    """Όλο το κείμενο ενός DOCX (διαδρομή ή bytes), με τη σειρά του εγγράφου.

    Διαβάζει: παραγράφους και πίνακες του κυρίως σώματος (και εμφωλευμένους
    πίνακες), πλαίσια κειμένου, πεδία περιεχομένου (content controls),
    κείμενο που προστέθηκε με παρακολούθηση αλλαγών, και στο τέλος
    κεφαλίδες, υποσέλιδα, υποσημειώσεις και σημειώσεις τέλους.

    Γιατί: παλαιότερα διαβάζονταν μόνο οι παράγραφοι και οι πίνακες του
    κυρίως σώματος. Κείμενο σε πλαίσιο κειμένου ή υποσέλιδο (π.χ. μοίρες ή
    orb στο έντυπο του πελάτη) δεν περνούσε από τον έλεγχο.
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    document = Document(source)

    # Διατηρείται η ΣΕΙΡΑ του εγγράφου (παράγραφοι και πίνακες όπως
    # εμφανίζονται). Παλαιότερα οι πίνακες προστίθεντο όλοι στο τέλος, οπότε
    # π.χ. η (τότε υποχρεωτική) τελική πρόταση φαινόταν να μην είναι τελευταία και
    # τα πλαίσια σύνοψης αποκόπτονταν από τον Οίκο τους.
    blocks = _block_lines(document.element.body)

    # Κεφαλίδες/υποσέλιδα: ίδιο κείμενο σε πολλές ενότητες μετράει μία φορά.
    extra, seen_parts = [], set()
    for section in document.sections:
        for hf in (
            section.header,
            section.first_page_header,
            section.even_page_header,
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        ):
            if hf.is_linked_to_previous:
                continue
            part = hf.part
            if id(part) in seen_parts:
                continue
            seen_parts.add(id(part))
            extra.extend(_block_lines(hf._element))

    for rel in document.part.rels.values():
        if rel.is_external or not rel.reltype.endswith(_NOTE_RELTYPES):
            continue
        from docx.oxml import parse_xml

        root = parse_xml(rel.target_part.blob)
        for note in root:
            if _local(note.tag) in ("footnote", "endnote") and note.get(_W + "type") in (
                None,
                "normal",
            ):
                extra.extend(_block_lines(note))

    for line in extra:
        # Αγνοούνται γραμμές χωρίς γράμματα/ψηφία (π.χ. « / » από αρίθμηση σελίδων).
        if any(ch.isalnum() for ch in line) and line not in blocks:
            blocks.append(line)
    return "\n".join(blocks)


@st.cache_data(show_spinner=False)
def load_default_references() -> tuple[str, str]:
    # @st.cache_data: το Streamlit ξανατρέχει ολόκληρο το script σε κάθε
    # interaction, οπότε χωρίς caching αυτά τα (συχνά εκτενή) .docx
    # ξαναδιαβάζονταν και ξαναπαρσάρονταν από τον δίσκο σε κάθε κλικ.
    #
    # Accept both repository layouts: a dedicated references/ folder or the
    # two DOCX files beside app.py.  This makes GitHub web uploads simpler.
    instructions = DEFAULT_INSTRUCTIONS if DEFAULT_INSTRUCTIONS.exists() else ROOT_INSTRUCTIONS
    style = DEFAULT_STYLE if DEFAULT_STYLE.exists() else ROOT_STYLE
    if not instructions.exists() or not style.exists():
        # Πριν έγραφε "...v4...", ενώ το πραγματικό αρχείο είναι Odigies_v5.docx
        # (και το app.py το παρουσιάζει ως "Ενσωματωμένες οδηγίες v5.3") --
        # ένα μήνυμα σφάλματος έπρεπε τουλάχιστον να συμφωνεί με το filename.
        raise FileNotFoundError("Λείπουν οι ενσωματωμένες οδηγίες v5 ή το πρότυπο ύφους.")
    return docx_text(instructions), docx_text(style)
