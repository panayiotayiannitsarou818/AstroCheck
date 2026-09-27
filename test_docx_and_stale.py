"""(α) Η ανάγνωση Word καλύπτει και τα «κρυφά» σημεία: πλαίσια κειμένου,
κεφαλίδες, υποσέλιδα, υποσημειώσεις, πεδία περιεχομένου, εμφωλευμένους
πίνακες και κείμενο παρακολούθησης αλλαγών.
(β) Ένα αποτέλεσμα ελέγχου δεν μένει ορατό όταν το ανεβασμένο Word άλλαξε.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import validator as V
from case_state import fingerprint, forget_stale_results
from models import Chart, Point
from reference_loader import docx_text

HIDDEN = Path(__file__).parent / "fixtures" / "hidden_places.docx"


@pytest.fixture(scope="module")
def hidden_text():
    return docx_text(HIDDEN.read_bytes())


@pytest.mark.parametrize(
    "snippet",
    [
        "Κυρίως κείμενο.",
        "Πλαίσιο: Κρόνος 14°02′",  # πλαίσιο κειμένου
        "Πεδίο περιεχομένου: Πλατιά αλλά έγκυρη",  # content control
        "Αλλαγές: προστέθηκε orb",  # παρακολούθηση αλλαγών (προσθήκη)
        "Εσωτερικός πίνακας: Πίνακας Astrodienst",  # εμφωλευμένος πίνακας
        "Κεφαλίδα: orb 1°13′",
        "Υποσέλιδο: Στενή/ισχυρή",
        "Υποσημείωση: Αφροδίτη 23°21′",
    ],
)
def test_hidden_places_are_read(hidden_text, snippet):
    assert snippet in hidden_text


def test_text_box_is_read_once_and_deleted_text_is_ignored(hidden_text):
    assert hidden_text.count("Πλαίσιο: Κρόνος 14°02′") == 1
    assert "ΔΙΑΓΡΑΜΜΕΝΟ" not in hidden_text


def test_body_order_is_kept_and_extras_come_last(hidden_text):
    lines = hidden_text.splitlines()
    assert lines[0] == "Κυρίως κείμενο."
    assert lines.index("Πλαίσιο: Κρόνος 14°02′") < lines.index("Κεφαλίδα: orb 1°13′")


def test_technical_data_in_hidden_places_fails_client_document(hidden_text):
    houses = "\n".join(f"{n}ος Οίκος\nΚείμενο." for n in range(1, 13))
    chart = Chart(points=[Point("x", "Σελήνη", "", 0, 0, 0, 0.0, 10)])
    r = V.validate_rewrite(chart, houses, houses + "\n" + hidden_text)
    assert not r.ok
    flagged = " ".join(sentence for _, sentence in r.technical_data)
    for snippet in ("Κρόνος 14°02′", "orb 1°13′", "Στενή/ισχυρή", "Αφροδίτη 23°21′", "Astrodienst"):
        assert snippet in flagged


def test_summary_box_lines_stay_separate():
    """Οι γραμμές ενός κελιού (π.χ. πλαίσιο σύνοψης) χωρίζονται όπως πριν."""
    from docx_builder import build_analysis_docx

    text = docx_text(
        build_analysis_docx("X", "1ος Οίκος\nΒασική δύναμη: α\nΚυβερνήτης: Άρης\nΤελικό συμπέρασμα: β")
    )
    assert "Κυβερνήτης: Άρης" in text.splitlines()


# ---------------------------------------------------------------------------
# Παλιό αποτέλεσμα για άλλο αρχείο
# ---------------------------------------------------------------------------
class State(SimpleNamespace):
    def pop(self, key, default=None):
        return self.__dict__.pop(key, default)


def _checked_rewrite(file_bytes=b"A", analysis="ANALYSIS"):
    return State(
        analysis=analysis,
        analysis_source="paste",
        rewrite_validation=SimpleNamespace(ok=True),
        rewrite_docx_bytes=file_bytes,
        rewrite_docx_name="a.docx",
        rewrite_docx_hash=fingerprint(file_bytes),
        rewrite_analysis_hash=fingerprint(analysis),
    )


def test_same_rewrite_file_keeps_result():
    s = _checked_rewrite()
    assert forget_stale_results(s, rewrite_upload=b"A") == []
    assert s.rewrite_validation.ok and s.rewrite_docx_bytes == b"A"


def test_new_rewrite_file_clears_result_and_download():
    s = _checked_rewrite()
    assert forget_stale_results(s, rewrite_upload=b"B") == ["rewrite"]
    assert s.rewrite_validation is None and s.rewrite_docx_bytes is None


def test_removed_rewrite_file_clears_result():
    s = _checked_rewrite()
    assert forget_stale_results(s, rewrite_upload=None) == ["rewrite"]


def test_changed_analysis_clears_rewrite_result():
    s = _checked_rewrite()
    s.analysis = "ΝΕΑ ΑΝΑΛΥΣΗ"
    assert forget_stale_results(s, rewrite_upload=b"A") == ["rewrite"]


def test_new_analysis_word_clears_analysis_and_rewrite():
    s = State(
        analysis="TEXT",
        analysis_source="docx",
        validation=SimpleNamespace(ok=True),
        analysis_docx_bytes=b"X",
        analysis_docx_name="x.docx",
        analysis_docx_hash=fingerprint(b"X"),
        rewrite_validation=SimpleNamespace(ok=True),
        rewrite_docx_bytes=b"A",
        rewrite_docx_name="a.docx",
        rewrite_docx_hash=fingerprint(b"A"),
        rewrite_analysis_hash=fingerprint("TEXT"),
    )
    assert forget_stale_results(s, analysis_upload=b"Y", rewrite_upload=b"A") == ["analysis", "rewrite"]
    assert s.validation is None and s.analysis_docx_bytes is None and s.analysis == ""
    assert s.rewrite_validation is None


def test_pasted_analysis_is_not_tied_to_an_uploaded_file():
    s = _checked_rewrite()
    s.validation = SimpleNamespace(ok=True)
    assert forget_stale_results(s, analysis_upload=None, rewrite_upload=b"A") == []
    assert s.validation.ok
