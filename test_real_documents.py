"""Πραγματικά έγγραφα (ανώνυμος χάρτης «P.» = astro_paradeigma_2): δύο
τεχνικές αναλύσεις και τα δύο τελικά έντυπά τους. Πρέπει να περνούν όπως
είναι, και να απορρίπτονται όταν αλλοιωθεί ένα μόνο δεδομένο."""

from pathlib import Path

import pytest

import validator as V
from parser import parse_astrodienst_pdf
from reference_loader import docx_text

ROOT = Path(__file__).parent / "fixtures"
REAL = ROOT / "real"
CASES = ["A", "B"]


@pytest.fixture(scope="module")
def chart():
    pdf = ROOT / "astro_paradeigma_2.pdf"
    return parse_astrodienst_pdf(pdf.read_bytes(), pdf.name)


def _texts(case):
    return (
        docx_text((REAL / f"P_analysi_{case}.docx").read_bytes()),
        docx_text((REAL / f"P_teliki_{case}.docx").read_bytes()),
    )


@pytest.mark.parametrize("case", CASES)
def test_real_documents_pass(chart, case):
    analysis, final = _texts(case)
    result = V.validate_analysis(chart, analysis)
    assert result.ok, result.details_lines()[:5]
    result = V.validate_rewrite(chart, analysis, final)
    assert result.ok, result.details_lines()[:5]


@pytest.mark.parametrize("case", CASES)
def test_structurally_similar_sentences_are_not_reported_as_the_same(chart, case):
    analysis, final = _texts(case)
    for warning in V.validate_rewrite(chart, analysis, final).warnings:
        if warning.startswith("Η ίδια πρόταση"):
            assert "Δίας" not in warning  # ο Δίας κυβερνά μόνο τον 1ο (και παραδοσιακά τον 4ο)


MUTATIONS = [
    ("Σελήνη–Ποσειδώνας", "Σελήνη–Κρόνος"),  # ανύπαρκτη όψη
    ("τετράγωνο Σελήνη–Ποσειδώνας", "τρίγωνο Σελήνη–Ποσειδώνας"),  # λάθος τύπος
    ("Κυβερνήτης του Οίκου είναι ο Δίας", "Κυβερνήτης του Οίκου είναι ο Άρης"),
    ("είναι η Σελήνη, στην Παρθένο", "είναι η Σελήνη, στον Λέοντα"),
    ("ο Ερμής, στον Υδροχόο και στον 2ο Οίκο", "ο Ερμής, στον Υδροχόο και στον 5ο Οίκο"),
]


@pytest.mark.parametrize("old,new", MUTATIONS, ids=[m[1] for m in MUTATIONS])
def test_one_altered_fact_in_the_client_document_is_rejected(chart, old, new):
    analysis, final = _texts("B")
    assert old in final
    result = V.validate_rewrite(chart, analysis, final.replace(old, new, 1))
    assert not result.ok


def test_style_a_ruler_sentence_with_wrong_house_is_rejected(chart):
    analysis, final = _texts("A")
    old = "είναι ο Δίας, που βρίσκεται στον Σκορπιό, στον 11ο Οίκο"
    assert old in final
    bad = final.replace(old, "είναι ο Δίας, που βρίσκεται στον Σκορπιό, στον 9ο Οίκο", 1)
    assert not V.validate_rewrite(chart, analysis, bad).ok


# --- χάρτες Γ. (ελληνικά) και K. (ελληνική ανάλυση, αγγλικό τελικό έντυπο) ----
from check_sheet import chart_from_check_sheet
from ui_texts import analysis_paste_message, detect_language, language_notes, rewrite_paste_message

SHEET_CASES = [
    ("G_deltio.docx", "G_analysi.docx", "G_teliki.docx"),
    ("K_deltio.docx", "K_analysi.docx", "K_final_en.docx"),
    ("T_deltio.docx", "T_analysi.docx", "T_teliki.docx"),
]


def _load(name):
    return docx_text((REAL / name).read_bytes())


def test_check_sheet_reconstructs_the_same_chart_as_the_pdf(chart):
    rebuilt = chart_from_check_sheet(_load("P_deltio.docx"))
    key = lambda c: {(frozenset((a.first, a.second)), a.aspect, a.orb_text, a.weight) for a in c.aspects}
    pos = lambda c: {(p.name, p.sign, p.degree, p.minute, p.house, p.retrograde) for p in c.points}
    assert key(rebuilt) == key(chart) and pos(rebuilt) == pos(chart)
    assert [c.sign for c in rebuilt.cusps] == [c.sign for c in chart.cusps]


@pytest.mark.parametrize("sheet,analysis,final", SHEET_CASES, ids=["G", "K-en", "T"])
def test_other_real_charts_pass(sheet, analysis, final):
    c = chart_from_check_sheet(_load(sheet))
    a, f = _load(analysis), _load(final)
    assert V.validate_analysis(c, a).ok
    result = V.validate_rewrite(c, a, f)
    assert result.ok, result.details_lines()[:5]


EN_MUTATIONS = [
    ("The ruler of this House is Mars, in Libra and in the 8th House", "The ruler of this House is Mars, in Libra and in the 5th House"),
    ("The ruler of this House is Mars, in Libra", "The ruler of this House is Mars, in Leo"),
    ("The ruler of this House is Mars", "The ruler of this House is the Moon"),
    ("square Jupiter–Chiron", "square Jupiter–Mars"),
    ("square Jupiter–Chiron", "trine Jupiter–Chiron"),
]


@pytest.mark.parametrize("old,new", EN_MUTATIONS, ids=[m[1] for m in EN_MUTATIONS])
def test_one_altered_fact_in_the_english_client_document_is_rejected(old, new):
    c = chart_from_check_sheet(_load("K_deltio.docx"))
    a, f = _load("K_analysi.docx"), _load("K_final_en.docx")
    assert old in f
    assert not V.validate_rewrite(c, a, f.replace(old, new, 1)).ok


def test_language_is_read_from_the_documents_not_assumed():
    a, f = _load("K_analysi.docx"), _load("K_final_en.docx")
    assert detect_language(a) == "el" and detect_language(f) == "en"
    message = rewrite_paste_message("K.", "Αγγλικά", a)
    assert message.startswith("ΓΛΩΣΣΑ ΠΑΡΑΔΟΤΕΟΥ: ΑΓΓΛΙΚΑ")  # η γλώσσα είναι η ΠΡΩΤΗ γραμμή
    assert "είναι στα ΕΛΛΗΝΙΚΑ" in message and "είναι στα αγγλικά" not in message
    assert "χωρίς να ρωτήσεις" in message and "«1st House»" in message
    assert "είναι στα αγγλικά" in rewrite_paste_message("K.", "Αγγλικά", f)
    # χωρίς φορτωμένη ανάλυση δεν υποθέτει γλώσσα πηγής
    unknown = rewrite_paste_message("K.", "Αγγλικά", "")
    assert unknown.startswith("ΓΛΩΣΣΑ ΠΑΡΑΔΟΤΕΟΥ: ΑΓΓΛΙΚΑ") and "είναι στα" not in unknown.split("\n\n")[0]
    assert "ΓΛΩΣΣΑ" not in rewrite_paste_message("G.", "Ελληνικά", a)
    assert rewrite_paste_message("G.", "Ελληνικά", f).startswith("ΓΛΩΣΣΑ ΠΑΡΑΔΟΤΕΟΥ: ΕΛΛΗΝΙΚΑ")
    assert analysis_paste_message("Αγγλικά").startswith("ΓΛΩΣΣΑ ΠΑΡΑΔΟΤΕΟΥ: ΑΓΓΛΙΚΑ")
    assert "ΓΛΩΣΣΑ" not in analysis_paste_message("Ελληνικά")
    assert language_notes("Αγγλικά", a, f) and "Δεν είναι σφάλμα" in language_notes("Αγγλικά", a, f)[0]
    assert len(language_notes("Αγγλικά", a, f)) == 1  # αγγλικό έντυπο: καμία ένσταση
    assert language_notes("Ελληνικά", a, f)  # ελληνική επιλογή, αγγλικό έντυπο


T_MUTATIONS = [
    ("είναι η Αφροδίτη, στην Παρθένο και στον 5ο Οίκο", "είναι η Αφροδίτη, στην Παρθένο και στον 8ο Οίκο"),
    ("Κυβερνήτης του Οίκου είναι η Αφροδίτη, στην Παρθένο", "Κυβερνήτης του Οίκου είναι η Αφροδίτη, στον Λέοντα"),
    ("Κυβερνήτης του Οίκου είναι η Αφροδίτη", "Κυβερνήτης του Οίκου είναι ο Δίας"),
    ("εξάγωνο Άρης–Δίας", "εξάγωνο Άρης–Ουρανός"),
    ("εξάγωνο Άρης–Δίας", "τετράγωνο Άρης–Δίας"),
    ("τρίγωνο Πλούτωνας–Μεσουράνημα", "τρίγωνο Κρόνος–Μεσουράνημα"),
]


@pytest.mark.parametrize("old,new", T_MUTATIONS, ids=[m[1] for m in T_MUTATIONS])
def test_one_altered_fact_in_chart_t_is_rejected(old, new):
    c = chart_from_check_sheet(_load("T_deltio.docx"))
    a, f = _load("T_analysi.docx"), _load("T_teliki.docx")
    assert old in f
    assert not V.validate_rewrite(c, a, f.replace(old, new, 1)).ok


# --- εντολή αναδιατύπωσης v9: μετρήσεις ύφους (δεν κλειδώνουν) -----------------
from validation_rewrite import _style_warnings


def test_style_notes_report_repeated_aspects_and_weight_labels_without_blocking():
    c = chart_from_check_sheet(_load("T_deltio.docx"))
    a, f = _load("T_analysi.docx"), _load("T_teliki.docx")
    result = V.validate_rewrite(c, a, f)
    assert result.ok  # οι μετρήσεις ύφους δεν κλειδώνουν τη λήψη
    notes = _style_warnings(f)
    assert any("25 από τις 25 όψεις" in n and "κανόνας 8" in n for n in notes)
    assert any("ετικέτα βαρύτητας" in n and "κανόνας 22" in n for n in notes)
    assert all(n in result.warnings for n in notes)


def test_style_notes_are_silent_for_text_that_follows_the_v9_rules():
    text = (
        "1ος Οίκος — Ταυτότητα\nΤο τετράγωνο Σελήνη–Ποσειδώνας μπορεί να δείχνει ευαισθησία.\n"
        "Κεντρικό θέμα: Η ανάγκη για σταθερό έδαφος μπορεί να συνυπάρχει με την ανάγκη για κίνηση.\n"
        "2ος Οίκος — Αξίες\nΗ ίδια ευαισθησία μπορεί να αγγίζει και τον τρόπο που ορίζεις την αξία σου.\n"
        "Κεντρικό θέμα: Η αξία εδώ μπορεί να χρειάζεται δικά της μέτρα.\n"
    )
    assert _style_warnings(text) == []


def test_long_central_theme_is_reported():
    text = "1ος Οίκος — Ταυτότητα\nΚείμενο.\nΚεντρικό θέμα: " + " ".join(["λέξη"] * 30) + "\n"
    assert any("Κεντρικά θέματα" in n for n in _style_warnings(text))
