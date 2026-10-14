"""v19.5: συνέχεια από εκεί που σταμάτησε (π.χ. τέλος υπολοίπου API)."""

import pytest
from streamlit.testing.v1 import AppTest

import generator as G
from case_state import fingerprint
from pipeline import run_full_pipeline
from test_v17_pipeline import CHART, COMMAND, ROOT, Fake


class NoCredit(Exception):
    status_code = 400

    def __str__(self):
        return "Your credit balance is too low"


def _validate(text):
    bad = text.count("ΛΑΘΟΣ")
    return Fake(bad == 0, ["ΛΑΘΟΣ"] * bad)


def test_resume_does_not_write_a_new_text_from_scratch():
    calls = []
    out = G.generate_validated(
        "k", "ΕΝΤΟΛΗ", _validate, start_text="κείμενο ΛΑΘΟΣ",
        complete=lambda k, t, m: calls.append(t) or "κείμενο σωστό",
    )
    assert out.ok and out.rounds[0].kind == "συνέχεια"
    assert len(calls) == 1 and "κείμενο ΛΑΘΟΣ" in calls[0]  # μόνο διόρθωση, πάνω στο υπάρχον


def test_resume_of_a_text_that_already_passes_costs_nothing():
    calls = []
    out = G.generate_validated("k", "Ε", _validate, start_text="έτοιμο", complete=lambda k, t, m: calls.append(t))
    assert out.ok and calls == []


def test_out_of_credit_mid_run_keeps_the_best_text():
    answers = iter(["α ΛΑΘΟΣ ΛΑΘΟΣ", "β ΛΑΘΟΣ"])

    def complete(k, t, m):
        try:
            return next(answers)
        except StopIteration:
            raise NoCredit()

    with pytest.raises(G.PermanentAPIError) as info:
        G.generate_validated("k", "Ε", _validate, complete=complete)
    assert "υπόλοιπο" in str(info.value)
    assert info.value.partial.text == "β ΛΑΘΟΣ"  # η καλύτερη απόπειρα δεν χάθηκε


def test_out_of_credit_on_the_very_first_call_has_nothing_to_keep():
    def complete(k, t, m):
        raise NoCredit()

    with pytest.raises(G.PermanentAPIError) as info:
        G.generate_validated("k", "Ε", _validate, complete=complete)
    assert getattr(info.value, "partial", None) is None


def _run(answers, **kw):
    it = iter(answers)
    calls = []

    def complete(k, t, m):
        calls.append(t)
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    result = run_full_pipeline(
        chart=CHART, personal={"Όνομα": "A."}, language="Ελληνικά", instructions_text="ο", style_text="υ",
        instructions_name="v6", style_name="υ", rewrite_command_text=COMMAND, api_key="k", provider="Claude",
        model="m", complete=complete, validate_analysis_fn=lambda c, t, p: _validate(t),
        validate_rewrite_fn=lambda c, a, t, p: _validate(t), content_review=False, **kw,
    )
    return result, calls


def test_pipeline_stopped_in_the_final_stage_keeps_the_approved_analysis():
    with pytest.raises(G.PermanentAPIError) as info:
        _run(["ανάλυση", "έντυπο ΛΑΘΟΣ", NoCredit()])
    partial = info.value.result
    assert partial.analysis_ok and partial.analysis_text == "ανάλυση"
    assert partial.final_text == "έντυπο ΛΑΘΟΣ"


def test_pipeline_resumes_in_the_final_stage_without_rewriting_the_analysis():
    result, calls = _run(["έντυπο σωστό"], resume_analysis="ανάλυση", resume_final="έντυπο ΛΑΘΟΣ")
    assert result.ok and result.analysis_text == "ανάλυση" and result.final_text == "έντυπο σωστό"
    assert len(calls) == 1 and "έντυπο ΛΑΘΟΣ" in calls[0]  # μία μόνο διόρθωση του εντύπου


def test_old_final_document_is_not_reused_if_the_analysis_changed():
    result, calls = _run(["ανάλυση νέα", "έντυπο νέο"], resume_analysis="ανάλυση ΛΑΘΟΣ", resume_final="έντυπο παλιό")
    assert result.ok and result.final_text == "έντυπο νέο"
    assert "έντυπο παλιό" not in calls[1]


def _key(chart):
    import checkpoint

    return checkpoint.chart_key(chart)


def test_app_offers_to_continue_and_keeps_the_draft():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.session_state["chart"] = CHART
    at.session_state["checkpoint"] = {"key": _key(CHART), "analysis": "1ος Οίκος\nκείμενο", "analysis_sig": "x", "done": False}
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [b.label for b in at.button]
    assert "▶️ Συνέχεια από εκεί που σταμάτησε" in labels or any(
        "ενεργοποίησε την πλήρη αυτόματη διαδικασία" in c.value for c in at.caption
    )
    assert any("μισοτελειωμένη εργασία" in m.value for m in at.markdown)


def test_checkpoint_of_another_chart_is_ignored():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.session_state["chart"] = CHART
    at.session_state["checkpoint"] = {"key": "άλλος χάρτης", "analysis": "κείμενο", "final": "", "done": False}
    at.run()
    assert not at.exception
    assert not any("μισοτελειωμένη εργασία" in m.value for m in at.markdown)


# --- v19.6: τα τρία κενά της αξιολόγησης ----------------------------------------
import checkpoint as CP
from types import SimpleNamespace


def test_timeout_in_the_final_stage_keeps_the_finished_analysis():
    progress = []
    with pytest.raises(TimeoutError) as info:
        _run(["ανάλυση", TimeoutError("δίκτυο")], on_progress=lambda st, t, ok: progress.append((st, t, ok)))
    assert info.value.result.analysis_ok and info.value.result.analysis_text == "ανάλυση"
    assert progress == [("Ανάλυση", "ανάλυση", True)]


def test_progress_is_saved_before_the_next_call():
    order = []

    def complete(k, t, m):
        order.append("κλήση")
        return "κείμενο σωστό" if len(order) > 1 else "κείμενο ΛΑΘΟΣ"

    G.generate_validated("k", "Ε", _validate, complete=complete, on_best=lambda t, ok: order.append(("αποθήκευση", t)))
    assert order == ["κλήση", ("αποθήκευση", "κείμενο ΛΑΘΟΣ"), "κλήση", ("αποθήκευση", "κείμενο σωστό")]


CHART_X = SimpleNamespace(name="A.", date="—", time="—", place="—", house_system="Placidus")


def _sigs(language="Ελληνικά", instructions="οδηγίες", hide=True):
    shared = SimpleNamespace(name="A.", date="—" if hide else "1/1/1990", time="—", place="—")
    a = CP.analysis_signature(language, instructions, "ύφος", shared)
    return a, CP.rewrite_signature(a, language, "εντολή")


def _cp_with_both(a, f):
    key = CP.chart_key(CHART_X)
    cp = CP.update(None, key, CP.STAGE_ANALYSIS, "ανάλυση", True, a, f)
    return CP.update(cp, key, CP.STAGE_REWRITE, "έντυπο ΛΑΘΟΣ", False, a, f), key


def test_same_settings_resume_both_stages():
    a, f = _sigs()
    cp, key = _cp_with_both(a, f)
    assert CP.resume_texts(cp, key, a, f) == ("ανάλυση", "έντυπο ΛΑΘΟΣ")


@pytest.mark.parametrize("changed", [dict(language="Αγγλικά"), dict(instructions="νέες οδηγίες"), dict(hide=False)])
def test_changed_settings_do_not_reuse_old_texts(changed):
    a, f = _sigs()
    cp, key = _cp_with_both(a, f)
    a2, f2 = _sigs(**changed)
    assert CP.resume_texts(cp, key, a2, f2) == ("", "")


def test_changed_rewrite_command_reuses_the_analysis_but_not_the_document():
    a, f = _sigs()
    cp, key = _cp_with_both(a, f)
    assert CP.resume_texts(cp, key, a, CP.rewrite_signature(a, "Ελληνικά", "νέα εντολή")) == ("ανάλυση", "")


def test_new_analysis_text_invalidates_the_old_document():
    a, f = _sigs()
    cp, key = _cp_with_both(a, f)
    cp = CP.update(cp, key, CP.STAGE_ANALYSIS, "ανάλυση διορθωμένη", True, a, f)
    assert CP.resume_texts(cp, key, a, f) == ("ανάλυση διορθωμένη", "")


def test_checkpoint_of_another_chart_is_never_used():
    a, f = _sigs()
    cp, _ = _cp_with_both(a, f)
    assert CP.resume_texts(cp, "άλλος", a, f) == ("", "") and not CP.resumable(cp, "άλλος")


def test_done_when_both_stages_pass():
    a, f = _sigs()
    cp, key = _cp_with_both(a, f)
    assert CP.resumable(cp, key)
    cp = CP.update(cp, key, CP.STAGE_REWRITE, "έντυπο σωστό", True, a, f)
    assert cp["done"] and not CP.resumable(cp, key)


def test_truncated_review_reply_is_charged_to_the_review_model():
    usage = G.Usage(model="claude-opus-5-5")
    exc = G.TruncatedOutput("κόπηκε")
    exc.input_tokens, exc.output_tokens = 100_000, 10_000
    usage.add_failure(exc, "claude-sonnet-5-5", main=False)
    # Sonnet: 0,1 × 2 + 0,01 × 10 = 0,30 $ (με Opus θα ήταν 0,60 $) · όχι κλήση δημιουργίας
    assert abs(usage.spent_usd - 0.30) < 1e-9 and usage.main_requests == 0 and usage.review_requests == 1


def test_reviewer_charges_its_own_truncated_replies_correctly():
    import content_review as CR

    usage = G.Usage(model="claude-opus-5-5")

    def reviewer(k, p, m):
        e = G.TruncatedOutput("κόπηκε")
        e.input_tokens, e.output_tokens = 100_000, 10_000
        raise e

    CR.with_content_review(lambda t: Fake(True), reviewer, "k", "claude-sonnet-5-5", CR.KIND_ANALYSIS, usage=usage)("κείμενο")
    assert usage.main_requests == 0 and usage.review_requests == CR.REVIEW_ATTEMPTS
    assert abs(usage.spent_usd - 0.30 * CR.REVIEW_ATTEMPTS) < 1e-9


# --- v19.7 -----------------------------------------------------------------------
import dataclasses


def test_chart_identity_includes_the_astrological_data():
    other = dataclasses.replace(CHART, points=list(CHART.points[:-1]))
    assert CP.chart_key(CHART) != CP.chart_key(other)


def test_changed_settings_invalidate_the_old_document_and_done_even_with_identical_text():
    a, f = _sigs()
    key = CP.chart_key(CHART_X)
    cp = CP.update(None, key, CP.STAGE_ANALYSIS, "ανάλυση", True, a, f)
    cp = CP.update(cp, key, CP.STAGE_REWRITE, "έντυπο", True, a, f)
    assert cp["done"]
    a2, f2 = _sigs(language="Αγγλικά")
    cp = CP.update(cp, key, CP.STAGE_ANALYSIS, "ανάλυση", True, a2, f2)  # ίδιο κείμενο, νέες ρυθμίσεις
    assert not cp["done"] and "final" not in cp and CP.resumable(cp, key)
    assert CP.resume_texts(cp, key, a2, f2) == ("ανάλυση", "")


def test_signature_is_stored_only_with_text_actually_generated():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    body = src[src.index("def _run_full_pipeline_ui("):src.index("def _auto_result_panel(")]
    assert "st.session_state.analysis_sig = a_sig" not in body
    store = src[src.index("def _store_pipeline_result("):src.index("def _run_full_pipeline_ui(")]
    assert store.index("if result.analysis_text:") < store.index("st.session_state.analysis_sig = analysis_sig")
