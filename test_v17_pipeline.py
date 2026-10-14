"""v17: πλήρης αυτόματη διαδικασία — ο χρήστης ανεβάζει μόνο το PDF."""
from dataclasses import dataclass, field
from pathlib import Path

from streamlit.testing.v1 import AppTest

from parser import parse_astrodienst_pdf
from pipeline import STAGE_ANALYSIS, STAGE_REWRITE, run_full_pipeline

ROOT = Path(__file__).parent
CHART = parse_astrodienst_pdf((ROOT / "fixtures" / "astro_paradeigma_2.pdf").read_bytes(), "astro_paradeigma_2.pdf")
COMMAND = "Η εντολή\nΚανόνες.\nΗμερολόγιο διορθώσεων ανά ανάλυση\nΥΠΟΧΡΕΩΤΙΚΟΣ ΤΕΛΙΚΟΣ ΕΛΕΓΧΟΣ ΑΜΕΤΑΒΛΗΤΩΝ ΔΕΔΟΜΕΝΩΝ\nΈλεγχος."


@dataclass
class Fake:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def summary(self):
        return "ok" if self.ok else "σφάλματα"

    def details_lines(self):
        return list(self.errors)


def _check(text):
    return Fake("ΛΑΘΟΣ" not in text, ["ΛΑΘΟΣ"] if "ΛΑΘΟΣ" in text else [])


def _run(answers, log=None, max_rounds=10):
    prompts = []
    it = iter(answers)
    result = run_full_pipeline(
        chart=CHART, personal={"Όνομα": "A."}, language="Ελληνικά", instructions_text="οδηγίες",
        style_text="ύφος", instructions_name="v6", style_name="ύφος", rewrite_command_text=COMMAND,
        api_key="k", provider="Claude", model="m", max_rounds=max_rounds,
        on_round=(lambda st, r: log.append((st, r.number, r.ok))) if log is not None else None,
        complete=lambda k, t, m: prompts.append(t) or next(it),
        validate_analysis_fn=lambda c, t, p: _check(t),
        validate_rewrite_fn=lambda c, a, t, p: _check(t),
        content_review=False,  # ο έλεγχος ΤΝ έχει δικές του δοκιμές (test_v19.py)
    )
    return result, prompts


def test_analysis_then_final_document_each_corrected_until_approved():
    log = []
    result, prompts = _run(["ανάλυση ΛΑΘΟΣ", "ανάλυση σωστή", "έντυπο ΛΑΘΟΣ", "έντυπο ΛΑΘΟΣ", "έντυπο σωστό"], log)
    assert result.ok and result.stopped_at is None
    assert result.analysis_text == "ανάλυση σωστή" and result.final_text == "έντυπο σωστό"
    assert log == [(STAGE_ANALYSIS, 1, False), (STAGE_ANALYSIS, 2, True),
                   (STAGE_REWRITE, 1, False), (STAGE_REWRITE, 2, False), (STAGE_REWRITE, 3, True)]
    # το τελικό έντυπο γράφεται από την ΕΓΚΕΚΡΙΜΕΝΗ ανάλυση
    assert "ανάλυση σωστή" in prompts[2] and "ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ ΤΕΛΙΚΗΣ ΑΝΑΔΙΑΤΥΠΩΣΗΣ" in prompts[2]


def test_final_document_is_not_written_from_an_unapproved_analysis():
    result, prompts = _run(["ΛΑΘΟΣ"] * 3, max_rounds=3)
    assert not result.ok and result.stopped_at == STAGE_ANALYSIS
    assert result.final_text == "" and len(prompts) == 3


def test_tab_one_offers_the_full_automatic_process():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    toggle = next(t for t in at.toggle if "Πλήρης αυτόματη διαδικασία" in t.label)
    assert toggle.value is True


def test_result_panel_offers_both_downloads_when_everything_is_approved():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.session_state["chart"] = CHART
    at.session_state["analysis"] = "1ος Οίκος\nκείμενο"
    at.session_state["validation"] = Fake(True)
    at.session_state["analysis_source"] = "api"
    at.session_state["rewrite_validation"] = Fake(True)
    from docx_builder import build_analysis_docx
    at.session_state["rewrite_docx_bytes"] = build_analysis_docx("A.", "1ος Οίκος\nΚείμενο.")
    at.session_state["rewrite_docx_name"] = "Teliki_Analysi.docx"
    at.session_state["rewrite_source"] = "api"
    from case_state import fingerprint
    at.session_state["rewrite_analysis_hash"] = fingerprint("1ος Οίκος\nκείμενο")
    at.session_state["auto_result"] = {"ok": True, "stopped_at": None, "analysis_rounds": 2, "final_rounds": 1, "name": "A."}
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    texts = " ".join(s.value for s in at.success)
    # v18: «πέρασε τους ελέγχους…» αντί για «εγκρίθηκε»
    assert "Η ανάλυση πέρασε τους ελέγχους" in texts and "Το τελικό έντυπο του πελάτη πέρασε τους ελέγχους" in texts
    assert "εγκρίθηκε" not in texts


def test_result_panel_explains_a_stalled_stop_and_shows_the_cost():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.session_state["chart"] = CHART
    at.session_state["analysis"] = "1ος Οίκος\nκείμενο"
    at.session_state["validation"] = Fake(False)
    at.session_state["analysis_source"] = "api"
    at.session_state["auto_result"] = {
        "ok": False, "stopped_at": "Ανάλυση", "analysis_rounds": 7, "final_rounds": 0, "name": "A.",
        "stop_reason": "στασιμότητα", "cap": 30, "usage": "7 αιτήματα · κόστος περίπου 3,10 € (3,60 $)",
    }
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    errors = " ".join(e.value for e in at.error)
    captions = " ".join(c.value for c in at.caption)
    assert "στασιμότητα" in errors and "3,10 €" in captions


def test_result_panel_explains_an_incomplete_content_review():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.session_state["chart"] = CHART
    at.session_state["analysis"] = "1ος Οίκος\nκείμενο"
    at.session_state["validation"] = Fake(False)
    at.session_state["analysis_source"] = "api"
    at.session_state["auto_result"] = {
        "ok": False, "stopped_at": "Ανάλυση", "analysis_rounds": 1, "final_rounds": 0, "name": "A.",
        "stop_reason": "ο έλεγχος περιεχομένου δεν ολοκληρώθηκε", "cap": 30, "usage": "",
    }
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    errors = " ".join(e.value for e in at.error)
    assert "ΔΕΝ θεωρείται ελεγμένο" in errors
