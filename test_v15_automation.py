"""v15: επιλογή παρόχου (Claude/OpenAI) και αυτόματη τελική αναδιατύπωση.
Καμία πραγματική κλήση API: το μοντέλο αντικαθίσταται από ψεύτικη συνάρτηση."""

import sys
import types
from pathlib import Path

import pytest

import generator as G
import validator as V
from check_sheet import chart_from_check_sheet
from docx_builder import build_analysis_docx
from reference_loader import docx_text
from ui_texts import rewrite_language_block

ROOT = Path(__file__).parent
REAL = ROOT / "fixtures" / "real"
COMMAND = ROOT / "Desmeftiki_Entoli_Telikis_Anadiatyposis_v9.docx"


def _load(name):
    return docx_text((REAL / name).read_bytes())


def test_providers_and_models():
    assert G.PROVIDERS == ("Claude", "OpenAI")
    assert G.completer("Claude") is G._anthropic_complete
    assert G.completer("OpenAI") is G._openai_complete
    assert G.DEFAULT_MODELS["Claude"].startswith("claude-")
    with pytest.raises(ValueError):
        G.completer("Άλλο")


def _fake_anthropic(monkeypatch, stop_reason, seen):
    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            block = types.SimpleNamespace(type="text", text="ΚΕΙΜΕΝΟ")
            thinking = types.SimpleNamespace(type="thinking")
            return types.SimpleNamespace(stop_reason=stop_reason, content=[thinking, block])

    class Client:
        def __init__(self, **kw):
            seen["client"] = kw
            self.messages = types.SimpleNamespace(stream=self._stream)

        def _stream(self, **kw):
            seen["request"] = kw
            return Stream()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=Client))


def test_claude_call_streams_and_returns_only_text(monkeypatch):
    seen = {}
    _fake_anthropic(monkeypatch, "end_turn", seen)
    assert G._anthropic_complete("κλειδί", "εντολή", "claude-opus-5-5") == "ΚΕΙΜΕΝΟ"
    assert seen["client"]["api_key"] == "κλειδί"
    assert seen["request"]["model"] == "claude-opus-5-5"
    assert seen["request"]["messages"] == [{"role": "user", "content": "εντολή"}]
    assert seen["request"]["max_tokens"] == G.ANTHROPIC_MAX_TOKENS


def test_truncated_claude_output_is_an_error_not_a_short_document(monkeypatch):
    _fake_anthropic(monkeypatch, "max_tokens", {})
    with pytest.raises(G.TruncatedOutput):
        G._anthropic_complete("κ", "ε", "claude-opus-5-5")


def test_rewrite_prompt_contains_rules_language_and_source_only():
    command = docx_text(COMMAND.read_bytes())
    analysis = _load("K_analysi.docx")
    block = rewrite_language_block("K.", "Αγγλικά", analysis)
    prompt = G.build_rewrite_prompt(command, analysis, "K.", block)
    assert prompt.startswith("ΓΛΩΣΣΑ ΠΑΡΑΔΟΤΕΟΥ: ΑΓΓΛΙΚΑ")
    assert "22. " in prompt and "23. " in prompt and "του/της K." in prompt
    assert "Ημερολόγιο διορθώσεων" not in prompt and "[[" not in prompt and "[ΟΝΟΜΑ]" not in prompt
    assert prompt.rstrip().endswith(analysis.strip()[-200:])
    assert rewrite_language_block("G.", "Ελληνικά", analysis) == ""


def test_automatic_rewrite_round_trip_with_a_real_document():
    """Ψεύτικο μοντέλο: 1ος γύρος με μία ανύπαρκτη όψη, 2ος το πραγματικό έντυπο.
    Το Word που χτίζει η εφαρμογή πρέπει να περνά ξανά τον έλεγχο όταν διαβαστεί."""
    chart = chart_from_check_sheet(_load("T_deltio.docx"))
    analysis, final = _load("T_analysi.docx"), _load("T_teliki.docx")
    bad = final.replace("εξάγωνο Άρης–Δίας", "εξάγωνο Άρης–Ουρανός", 1)
    outputs, prompts = iter([bad, final]), []

    def complete(key, text, model):
        prompts.append(text)
        return next(outputs)

    command = docx_text(COMMAND.read_bytes())
    outcome = G.generate_validated(
        "κ",
        G.build_rewrite_prompt(command, analysis, "Γ.Τ.", ""),
        validate=lambda t: V.validate_rewrite(chart, analysis, t),
        complete=complete,
        revision_template=G.REWRITE_REVISION_TEMPLATE,
    )
    assert outcome.ok and [r.ok for r in outcome.rounds] == [False, True]
    assert "ΤΕΛΙΚΟ ΕΝΤΥΠΟ ΠΡΟΣ ΔΙΟΡΘΩΣΗ" in prompts[1] and "Άρης–Ουρανός" in prompts[1]
    word = build_analysis_docx("Γ.Τ.", outcome.text)
    assert V.validate_rewrite(chart, analysis, docx_text(word)).ok


def test_api_made_document_is_not_discarded_as_stale():
    from case_state import fingerprint, forget_stale_results

    state = types.SimpleNamespace(
        analysis="ανάλυση", analysis_source="api", analysis_docx_hash=None,
        rewrite_validation=object(), rewrite_docx_bytes=b"x", rewrite_docx_name="t.docx",
        rewrite_docx_hash=None, rewrite_analysis_hash=fingerprint("ανάλυση"), rewrite_source="api",
    )
    assert forget_stale_results(state, None, None) == []
    state.analysis = "άλλη ανάλυση"
    assert forget_stale_results(state, None, None) == ["rewrite"]


def test_app_renders_without_error():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
