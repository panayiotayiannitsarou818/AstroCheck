import re
from io import BytesIO
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from prompts import fmt
from astrology import movement_text
import lexicon_en as EN


def _shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


# Αναγνωρίζει **έντονα**, *πλάγια* και ***και τα δύο***· δεν πειράζει απλό
# κείμενο χωρίς αστερίσκους. Χρησιμοποιείται αντί για αφαίρεση των αστερίσκων,
# ώστε η έμφαση του μοντέλου να φτάνει πραγματικά στο Word.
_INLINE_MD = re.compile(r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|\*.+?\*)")
_NUMBERED_LIST = re.compile(r"^(\d+)\.\s+(.+)$")


def _add_formatted_runs(paragraph, text):
    for chunk in _INLINE_MD.split(text):
        if not chunk:
            continue
        if chunk.startswith("***") and chunk.endswith("***") and len(chunk) > 6:
            r = paragraph.add_run(chunk[3:-3])
            r.bold = True
            r.italic = True
        elif chunk.startswith("**") and chunk.endswith("**") and len(chunk) > 4:
            r = paragraph.add_run(chunk[2:-2])
            r.bold = True
        elif chunk.startswith("*") and chunk.endswith("*") and len(chunk) > 2:
            r = paragraph.add_run(chunk[1:-1])
            r.italic = True
        else:
            paragraph.add_run(chunk)


def _add_multiline(doc, text):
    """Προσθέτει το `text` ως ένα Word paragraph ανά γραμμή.

    Το python-docx (και το OOXML γενικότερα) ΔΕΝ μετατρέπει ένα literal '\\n'
    μέσα σε run σε ορατή αλλαγή γραμμής -- το Word δείχνει ένα συνεχόμενο
    μπλοκ κειμένου. Το build_audit_docx καλούσε d.add_paragraph(prompt) μία
    φορά με ολόκληρη την πολυσέλιδη εντολή (όλοι οι 12 Οίκοι, οι πλήρεις
    οδηγίες v4, το πρότυπο ύφους) ως ένα string, οπότε έβγαινε ένα άμορφο
    μπλοκ ~88.000 χαρακτήρων χωρίς ορατά όρια ενοτήτων. Εδώ σπάει σε πραγματικές
    γραμμές πρώτα, ώστε κάθε γραμμή -- ακόμη και οι κενές, που γίνονται κενά
    paragraphs -- να είναι δικό της paragraph, όπως ακριβώς η υπόλοιπη δομή
    αυτού του εγγράφου.
    """
    for line in text.splitlines():
        doc.add_paragraph(line)


def build_audit_docx(chart, personal, prompt):
    d = Document()
    sec = d.sections[0]
    sec.top_margin = Inches(0.7)
    sec.bottom_margin = Inches(0.7)
    sec.left_margin = Inches(0.75)
    sec.right_margin = Inches(0.75)
    styles = d.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(10.5)
    for s, size, color in [
        ("Title", 26, "1D3A34"),
        ("Heading 1", 18, "1D3A34"),
        ("Heading 2", 14, "5B7F6A"),
    ]:
        styles[s].font.name = "Aptos Display"
        styles[s].font.size = Pt(size)
        styles[s].font.color.rgb = RGBColor.from_string(color)
    title = d.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("AstroCheck — Δελτίο ελέγχου")
    # Το διορθωμένο όνομα (personal["Όνομα"]) είναι η πηγή αλήθειας, ίδια
    # λογική με το build_master_prompt -- ώστε ο τίτλος αυτού του Δελτίου
    # Ελέγχου να συμφωνεί πάντα με ό,τι βλέπει το μοντέλο μέσα στην εντολή.
    display_name = (personal.get("Όνομα") or "").strip() or chart.name
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(display_name).bold = True
    d.add_heading("Βασικά δεδομένα", 1)
    table = d.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for a, b in [
        ("Ημερομηνία", chart.date),
        ("Ώρα", chart.time),
        ("Τόπος", chart.place),
        ("Σύστημα Οίκων", chart.house_system),
    ]:
        cells = table.add_row().cells
        cells[0].text = a
        cells[1].text = b
        _shade(cells[0], "E5EFE8")
    d.add_heading("Πλανήτες και σημεία", 1)
    t = d.add_table(rows=1, cols=4)
    t.style = "Table Grid"
    for i, h in enumerate(["Σημείο", "Θέση", "Οίκος", "Κίνηση"]):
        t.rows[0].cells[i].text = h
        _shade(t.rows[0].cells[i], "1D3A34")
        t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
    for pnt in chart.points:
        c = t.add_row().cells
        c[0].text = pnt.name
        c[1].text = fmt(pnt)
        c[2].text = str(pnt.house or "—")
        c[3].text = movement_text(pnt)
    d.add_heading("Υποχρεωτικός έλεγχος τετραγώνων και αντιθέσεων", 1)
    hard = [a for a in chart.aspects if a.aspect in ("Τετράγωνο", "Αντίθεση")]
    t = d.add_table(rows=1, cols=4)
    t.style = "Table Grid"
    for i, h in enumerate(["Ζεύγος", "Όψη", "Orb", "Βαρύτητα"]):
        t.rows[0].cells[i].text = h
        _shade(t.rows[0].cells[i], "1D3A34")
        t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
    for a in hard:
        c = t.add_row().cells
        c[0].text = f"{a.first}–{a.second}"
        c[1].text = a.aspect
        c[2].text = a.orb_text
        c[3].text = a.weight
    d.add_page_break()
    d.add_heading("Πλήρης εντολή για δημιουργία ανάλυσης", 1)
    _add_multiline(d, prompt)
    bio = BytesIO()
    d.save(bio)
    return bio.getvalue()


_HOUSE_HEADING_RE = re.compile(
    r"^\d{1,2}ος\s+Ο[ιί]κος|^\d{1,2}(?:st|nd|rd|th)\s+House\b", re.IGNORECASE
)
_APPENDIX_HEADING_RE = re.compile(
    r"^Παράρτημα\s+επιβεβαιωμένων\s+όψεων|^Appendix\s+of\s+confirmed\s+aspects", re.IGNORECASE
)
_SUMMARY_START_RE = re.compile(r"^(?:Βασική\s+δύναμη|Key\s+strength)\s*[:\-]", re.IGNORECASE)
_SUMMARY_LABELS = ("Βασική δύναμη", "Βασική πρόκληση", "Κυβερνήτης", "Τελικό συμπέρασμα") + tuple(
    EN.SUMMARY_LABELS
)


def _add_page_number_field(paragraph):
    """PAGE / NUMPAGES στο footer -- το Odigies (§18) ζητά αριθμημένες
    σελίδες· το build_analysis_docx δεν το έκανε καθόλου πριν."""

    def field(instr):
        run = paragraph.add_run()
        f1 = OxmlElement("w:fldChar")
        f1.set(qn("w:fldCharType"), "begin")
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = instr
        f2 = OxmlElement("w:fldChar")
        f2.set(qn("w:fldCharType"), "end")
        run._r.append(f1)
        run._r.append(it)
        run._r.append(f2)

    field("PAGE")
    paragraph.add_run(" / ")
    field("NUMPAGES")


def _clean_summary_label(line):
    """Αφαιρεί bullet/markdown από μια γραμμή πλαισίου σύνοψης, κρατώντας
    'Ετικέτα: τιμή' έτοιμο για bold-label εμφάνιση."""
    line = line.lstrip("-•* ").strip()
    line = line.replace("**", "")
    return line


def _add_summary_box(doc, lines):
    """Πλαίσιο σύνοψης Οίκου ως πίνακας ενός κελιού με cantSplit -- έτσι
    μένει εγγυημένα ολόκληρο στην ίδια σελίδα (Odigies §11/§18), αντί για
    απλές παραγράφους που το Word μπορεί να σπάσει ανάμεσα σε δύο σελίδες."""
    table = doc.add_table(rows=1, cols=1)
    table.autofit = True
    row = table.rows[0]
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    cell = row.cells[0]
    _shade(cell, "EEF2F6")
    cell.paragraphs[0].text = ""
    first = True
    for raw in lines:
        text = _clean_summary_label(raw)
        if not text:
            continue
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        label_matched = False
        for label in _SUMMARY_LABELS:
            if text.lower().startswith(label.lower()):
                rest = text[len(label) :].lstrip(": ").strip()
                r = p.add_run(label + ": ")
                r.bold = True
                _add_formatted_runs(p, rest)
                label_matched = True
                break
        if not label_matched:
            _add_formatted_runs(p, text)
    doc.add_paragraph()  # μικρό κενό μετά το πλαίσιο, πριν τον επόμενο Οίκο


# ---------------------------------------------------------------------------
# v17.1: καλαίσθητο Word ΚΑΙ από απλό κείμενο.
# ---------------------------------------------------------------------------
# Η αυτόματη διαδρομή επιστρέφει απλό κείμενο (τίτλοι σε δική τους γραμμή,
# χωρίς Markdown). Πριν, ό,τι δεν είχε «#» έβγαινε απλή παράγραφος: Οίκοι,
# ενότητες και γραμμές όψεων χωρίς καμία ιεραρχία. Τώρα η δομή αναγνωρίζεται
# από το περιεχόμενο. Το ΚΕΙΜΕΝΟ δεν αλλάζει -- μόνο η μορφή -- ώστε το Word να
# περνά τον ίδιο έλεγχο με το κείμενο από το οποίο φτιάχτηκε.
_MAJOR_SECTION_RE = re.compile(
    r"^(?:\d{1,2}[.)]\s*)?(?:"
    r"Μεθοδολογία(?:\s+και\s+όρια[^\n]*)?|Όρια\s+της\s+ερμηνείας|Πώς\s+να\s+διαβάσεις[^\n]*"
    r"|Τελική\s+συνθετική\s+εικόνα|Τελική\s+σύνθεση|Συμβολική\s+κατεύθυνση\s+εξέλιξης"
    r"|Προτάσεις\s+προσωπικής\s+(?:ανάπτυξης|εξέλιξης)[^\n]*|Παράρτημα[^\n]*"
    r"|Δεύτερος\s+(?:μαθηματικός|τελικός)[^\n]*έλεγχος[^\n]*|Τελικός\s+(?:μαθηματικός\s+)?έλεγχος[^\n]*"
    r"|Methodology[^\n]*|Limits\s+of\s+(?:the\s+)?interpretation|Final\s+synthesis[^\n]*"
    r"|Symbolic\s+direction\s+of\s+(?:growth|evolution|development)|Suggestions\s+for\s+personal[^\n]*"
    r"|Personal\s+(?:growth|development)\s+suggestions|Appendix[^\n]*|(?:Second\s+)?Final\s+check[^\n]*"
    r")\s*$",
    re.IGNORECASE,
)
_THEME_RE = re.compile(r"^(Κεντρικό\s+θέμα|Central\s+theme)\s*:\s*(.*)$", re.IGNORECASE)
_ASPECT_LINE_RE = re.compile(r"^[-•*]?\s*\S+(?:\s\S+)?–\S+(?:\s\S+)?\s.+\(orb\s*\d", re.IGNORECASE)
_TERMINAL = tuple(".;:!?…,»)")


def _md_core(line: str) -> str:
    core = line.strip()
    for prefix in ("### ", "## ", "# "):
        if core.startswith(prefix):
            core = core[len(prefix):]
            break
    return core


def _plain(line: str) -> str:
    return _md_core(line).replace("**", "").lstrip("-•* ").strip()


def _looks_like_subheading(line: str, next_line: str) -> bool:
    """Σύντομη γραμμή-τίτλος (π.χ. «Πού βρίσκεται ο Οίκος», «Η πρακτική
    εφαρμογή») που ακολουθείται από παράγραφο κειμένου."""
    t = _plain(line)
    if not t or "|" in t or len(t) > 80 or len(t.split()) > 10 or t.endswith(_TERMINAL):
        return False
    if not t[0].isalpha() or not t[0].isupper():
        return False
    if _THEME_RE.match(t) or _SUMMARY_START_RE.match(t) or _ASPECT_LINE_RE.match(t):
        return False
    nxt = _plain(next_line) if next_line else ""
    return len(nxt) > len(t) + 20 or bool(_SUMMARY_START_RE.match(nxt)) or bool(_ASPECT_LINE_RE.match(nxt))


def _para_border(paragraph, color: str, fill: str | None = None, side: str = "left", size: int = 18):
    pPr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    edge = OxmlElement(f"w:{side}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), str(size))
    edge.set(qn("w:space"), "8")
    edge.set(qn("w:color"), color)
    bdr.append(edge)
    pPr.append(bdr)
    if fill:
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        pPr.append(shd)


def _add_pipe_table(doc, rows, accent: str):
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for i, cells in enumerate(rows):
        row = table.rows[i]
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for j in range(cols):
            cell = row.cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(cells[j] if j < len(cells) else "")
            run.font.size = Pt(9.5)
            if i == 0 and len(rows) > 1 and all(not any(ch.isdigit() for ch in c) for c in cells):
                run.bold = True
                _shade(cell, accent)
    doc.add_paragraph()


def build_analysis_docx(title_name, analysis):
    client = bool(re.search(r"^\s*(?:\*\*)?(?:Κεντρικό\s+θέμα|Central\s+theme)\s*:", analysis, re.IGNORECASE | re.MULTILINE))
    english = EN.looks_english(analysis)
    body_font, head_font = ("Georgia", "Georgia") if client else ("Calibri", "Calibri")
    navy, gold, grey = "23304F", "9C7A3C", "5C606B"

    d = Document()
    sec = d.sections[0]
    sec.top_margin = Inches(0.9)
    sec.bottom_margin = Inches(0.85)
    sec.left_margin = Inches(0.95)
    sec.right_margin = Inches(0.95)
    normal = d.styles["Normal"]
    normal.font.name = body_font
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.22
    for s, size, color, bold in [
        ("Title", 26, navy, False),
        ("Heading 1", 18, navy, False),
        ("Heading 2", 13, gold, True),
        ("Heading 3", 11.5, navy, True),
    ]:
        st_ = d.styles[s]
        st_.font.name = head_font
        st_.font.size = Pt(size)
        st_.font.bold = bold
        st_.font.color.rgb = RGBColor.from_string(color)
        st_.paragraph_format.keep_with_next = True
        rpr = st_.element.get_or_add_rPr()
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rpr.append(rf)
        for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rf.set(qn(k), head_font)
        for k in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            if rf.get(qn(k)) is not None:
                del rf.attrib[qn(k)]

    p = d.add_paragraph(style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if client:
        p.add_run("Your Birth Chart" if english else "Ο γενέθλιος χάρτης σου")
    else:
        p.add_run("Complete Astrological Analysis" if english else "Πλήρης Αστρολογική Ανάλυση")
    s = d.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = s.add_run(title_name)
    name_run.bold = True
    name_run.font.size = Pt(15)
    name_run.font.color.rgb = RGBColor.from_string(navy)

    footer_p = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_page_number_field(footer_p)

    lines = analysis.splitlines()
    i = 0
    seen_major = False
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if not line:
            i += 1
            continue
        core = _md_core(line)
        plain = _plain(line)
        nxt = next((l for l in lines[i + 1:] if l.strip()), "")

        # Πλαίσιο σύνοψης Οίκου -> πίνακας ενός κελιού (όπως πριν)
        if _SUMMARY_START_RE.match(plain):
            # v17.1: μόνο οι γραμμές με ετικέτα πλαισίου -- όχι «μέχρι την κενή
            # γραμμή», γιατί το απλό κείμενο συχνά δεν έχει κενές γραμμές και το
            # πλαίσιο κατάπινε όλο το υπόλοιπο κείμενο.
            box_lines = [line]
            j = i + 1
            while j < len(lines):
                nxt_plain = _plain(lines[j])
                if not nxt_plain:
                    break
                if not any(nxt_plain.lower().startswith(lbl.lower()) for lbl in _SUMMARY_LABELS):
                    break
                box_lines.append(lines[j].strip())
                j += 1
            _add_summary_box(d, box_lines)
            i = j
            continue

        # Τίτλος πλαισίου σύνοψης («Πλαίσιο σύνοψης …») -> μικρός τίτλος δεμένος με το πλαίσιο
        if re.match(r"^(?:Πλαίσιο\s+σύνοψης|Summary\s+box)\b", plain, re.IGNORECASE) and len(plain) <= 60:
            hp = d.add_heading("", 3)
            hp.paragraph_format.keep_with_next = True
            _add_formatted_runs(hp, plain)
            i += 1
            continue

        # Γραμμές πίνακα «α | β | γ» -> πίνακας
        if core.count("|") >= 1 and not _ASPECT_LINE_RE.match(plain) and nxt.count("|") >= 1 or core.count("|") >= 2:
            rows = []
            j = i
            while j < len(lines) and lines[j].strip() and _md_core(lines[j]).count("|") >= 1:
                cells = [c.strip().replace("**", "") for c in _md_core(lines[j]).strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):  # γραμμή διαχωρισμού Markdown
                    rows.append(cells)
                j += 1
            if rows and not _ASPECT_LINE_RE.match(_plain(lines[i])):
                _add_pipe_table(d, rows, "F3EFE6")
                i = j
                continue

        # Τίτλος Οίκου / κύριας ενότητας -> Heading 1 σε νέα σελίδα
        if _HOUSE_HEADING_RE.match(plain) or _MAJOR_SECTION_RE.match(plain):
            h = d.add_heading("", 1)
            if seen_major or _HOUSE_HEADING_RE.match(plain):
                h.paragraph_format.page_break_before = True
            seen_major = True
            _add_formatted_runs(h, plain)
            _para_border(h, "C9AE7C", side="bottom", size=6)
            i += 1
            continue

        # «Κεντρικό θέμα:» -> πλαίσιο έμφασης
        m = _THEME_RE.match(plain)
        if m:
            cp = d.add_paragraph()
            cp.paragraph_format.keep_together = True
            cp.paragraph_format.space_before = Pt(8)
            r = cp.add_run(m.group(1) + ": ")
            r.bold = True
            r.font.color.rgb = RGBColor.from_string(gold)
            r2 = cp.add_run(m.group(2).replace("**", ""))
            r2.italic = True
            r2.font.color.rgb = RGBColor.from_string(navy)
            _para_border(cp, "A07C3E", fill="F7F2E8")
            i += 1
            continue

        # Δομημένη γραμμή όψης «Α–Β Τύπος (orb …, …)» -> συμπαγής γραμμή
        if _ASPECT_LINE_RE.match(plain):
            ap = d.add_paragraph()
            ap.paragraph_format.space_after = Pt(0)
            ap.paragraph_format.line_spacing = 1.05
            ap.paragraph_format.left_indent = Inches(0.1)
            ap.paragraph_format.keep_with_next = bool(nxt and _ASPECT_LINE_RE.match(_plain(nxt)))
            run = ap.add_run(plain)
            run.font.size = Pt(9.5)
            _para_border(ap, navy, fill="F4F6F9")
            if not (nxt and _ASPECT_LINE_RE.match(_plain(nxt))):
                ap.paragraph_format.space_after = Pt(8)
            i += 1
            continue

        if line.startswith("### "):
            _add_formatted_runs(d.add_heading("", 3), line[4:])
        elif line.startswith("## "):
            _add_formatted_runs(d.add_heading("", 2), line[3:])
        elif line.startswith("# "):
            _add_formatted_runs(d.add_heading("", 1), line[2:])
        elif line.startswith(("- ", "• ")):
            _add_formatted_runs(d.add_paragraph(style="List Bullet"), line[2:])
        elif (core.startswith("**") and core.endswith("**") and len(plain) <= 90) or _looks_like_subheading(line, nxt):
            _add_formatted_runs(d.add_heading("", 2), plain)
        else:
            m = _NUMBERED_LIST.match(line)
            if m:
                _add_formatted_runs(d.add_paragraph(style="List Number"), m.group(2))
            else:
                bp = d.add_paragraph()
                bp.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                # το «Κεντρικό θέμα» δεν μένει μόνο του στην αρχή σελίδας
                if nxt and _THEME_RE.match(_plain(nxt)):
                    bp.paragraph_format.keep_with_next = True
                _add_formatted_runs(bp, line)
        i += 1
    bio = BytesIO()
    d.save(bio)
    return bio.getvalue()
