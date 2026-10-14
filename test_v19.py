"""v19: πλαίσιο Οίκων, έλεγχος περιεχομένου με ΤΝ, επανάληψη στην ανάλυση,
κόστος (έλεγχος πριν την κλήση, κομμένες απαντήσεις, τιμές, κοινός μετρητής)."""

import json

import pytest

import content_review as CR
import generator as G
import validation_safety as S
from case_state import CASE_STATE_KEYS
from house_framework import HOUSES, framework_block
from pipeline import run_full_pipeline
from test_english import build_analysis, chart2  # noqa: F401 (fixture)
from test_v17_pipeline import CHART, COMMAND, Fake

# --- 1. Πλαίσιο Οίκων ---------------------------------------------------------


def test_framework_covers_all_twelve_houses_with_limits_and_examples():
    assert [h.number for h in HOUSES] == list(range(1, 13))
    for h in HOUSES:
        assert h.topics and h.limits and h.good and h.bad
    block = framework_block()
    assert "6ος Οίκος" in block and "νόσος" in block
    assert "8ος Οίκος" in block and "θάνατος" in block


def test_framework_examples_of_wrong_wording_are_caught_by_the_word_filter_or_marked_wrong():
    # Τα «ακατάλληλα» παραδείγματα είναι παραδείγματα ΑΠΑΓΟΡΕΥΜΕΝΟΥ ύφους· τα
    # «κατάλληλα» δεν πρέπει να κόβονται από τον έλεγχο λέξεων.
    for h in HOUSES:
        assert S.unsafe_claims(h.good) == [], h.good


def test_framework_is_in_the_analysis_prompt(chart2):
    from prompts import build_master_prompt

    prompt = build_master_prompt(chart2, {"Όνομα": "A."}, "Ελληνικά", "οδηγίες", "ύφος", "v6", "ύφος")
    assert "ΠΛΑΙΣΙΟ ΕΡΜΗΝΕΙΑΣ ΑΝΑ ΟΙΚΟ" in prompt


def test_framework_is_in_the_rewrite_prompt():
    prompt = G.build_rewrite_prompt(COMMAND, "1ος Οίκος\nκείμενο", "A.", "")
    assert "ΠΛΑΙΣΙΟ ΕΡΜΗΝΕΙΑΣ ΑΝΑ ΟΙΚΟ" in prompt and "βασικές ερμηνείες" in prompt


# --- 2. Έλεγχος περιεχομένου με ΤΝ -------------------------------------------
TEXT = "1ος Οίκος — Ταυτότητα\nΟ Δίας μπορεί να δείχνει ζεστή παρουσία. Θα αποκτήσεις μεγάλη περιουσία."


def _reply(*issues):
    return json.dumps({"issues": list(issues)}, ensure_ascii=False)


ISSUE = {
    "sentence": "Θα αποκτήσεις μεγάλη περιουσία.",
    "rule": 2,
    "severity": "σοβαρό",
    "reason": "μελλοντικό γεγονός ως βέβαιο",
    "fix": "Μπορεί να χτίζεις ασφάλεια σταδιακά.",
}


def test_parse_review_reads_json_even_with_extra_text():
    issues = CR.parse_review("Ορίστε:\n" + _reply(ISSUE) + "\nτέλος")
    assert len(issues) == 1 and issues[0].severity == CR.SEVERE and issues[0].rule == "2"


@pytest.mark.parametrize("raw", ["", "δεν βρήκα τίποτα", "{χαλασμένο json", '{"issues": "όχι λίστα"}'])
def test_unreadable_review_returns_none(raw):
    assert CR.parse_review(raw) is None


def test_empty_review_means_no_issues():
    assert CR.parse_review(_reply()) == []


def _wrapped(replies, base_ok=True, calls=None):
    it = iter(replies)

    def reviewer(k, prompt, m):
        if calls is not None:
            calls.append(prompt)
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    return CR.with_content_review(lambda t: Fake(base_ok), reviewer, "k", "rev", CR.KIND_ANALYSIS)


def test_severe_issue_found_in_the_text_blocks_and_is_sent_for_correction():
    r = _wrapped([_reply(ISSUE)])(TEXT)
    assert not r.ok and r.blocking_issues
    assert any("Θα αποκτήσεις μεγάλη περιουσία" in line and "Διόρθωση" in line for line in r.details_lines())
    assert "έλεγχος περιεχομένου" in r.summary()


def test_severe_issue_not_found_in_the_text_is_reviewed_again_and_dropped_if_it_disappears():
    fake = dict(ISSUE, sentence="Μια πρόταση που δεν υπάρχει πουθενά στο κείμενο.")
    calls = []
    r = _wrapped([_reply(fake), _reply()], calls=calls)(TEXT)
    assert r.ok and len(calls) == 2


def test_severe_issue_not_found_that_persists_still_blocks():
    fake = dict(ISSUE, sentence="Μια πρόταση που δεν υπάρχει πουθενά στο κείμενο.")
    r = _wrapped([_reply(fake), _reply(fake)])(TEXT)
    assert not r.ok and any("δεν εντοπίστηκε αυτολεξεί" in line for line in r.details_lines())


def test_slightly_paraphrased_quote_counts_as_found():
    near = dict(ISSUE, sentence="Θα αποκτήσεις τελικά μεγάλη περιουσία")
    calls = []
    r = _wrapped([_reply(near)], calls=calls)(TEXT)
    assert not r.ok and len(calls) == 1 and r.content_issues[0].verified


def test_mild_issue_is_only_a_note():
    r = _wrapped([_reply(dict(ISSUE, severity="ήπιο"))])(TEXT)
    assert r.ok and len(r.warnings) == 1


def test_review_is_skipped_while_the_data_check_fails():
    calls = []
    r = _wrapped([_reply(ISSUE)], base_ok=False, calls=calls)(TEXT)
    assert not r.ok and calls == []


def test_review_that_recovers_on_a_later_attempt_is_used():
    calls = []
    r = _wrapped([TimeoutError("δίκτυο"), "όχι json", _reply()], calls=calls)(TEXT)
    assert r.ok and len(calls) == 3


def test_failed_review_blocks_the_text_fail_closed():
    calls = []
    r = _wrapped([TimeoutError("x"), "όχι json", '{"issues": "όχι λίστα"}'], calls=calls)(TEXT)
    assert not r.ok and r.review_incomplete and len(calls) == CR.REVIEW_ATTEMPTS
    assert CR.REVIEW_FAILED_PREFIX in r.summary()
    assert any("δεν θεωρείται ελεγμένο" in line for line in r.details_lines())


@pytest.mark.parametrize(
    "raw",
    [
        '{"issues": [{"rule": 2, "severity": "σοβαρό"}]}',  # χωρίς απόσπασμα
        '{"issues": ["σκέτο κείμενο"]}',  # εύρημα που δεν είναι αντικείμενο
        '{"issues": [{"sentence": ""}]}',
        '{"problems": []}',  # λάθος κλειδί
    ],
)
def test_malformed_reply_is_not_accepted(raw):
    assert CR.parse_review(raw) is None
    r = _wrapped([raw] * CR.REVIEW_ATTEMPTS)(TEXT)
    assert not r.ok and r.review_incomplete


@pytest.mark.parametrize(
    "bad",
    [
        dict(ISSUE, severity="high"),  # άγνωστη σοβαρότητα
        dict(ISSUE, severity=None),
        dict(ISSUE, rule=9),  # κανόνας εκτός λίστας
        dict(ISSUE, rule=6),  # ο 6 υπάρχει μόνο στο τελικό έντυπο
        dict(ISSUE, rule=True),
        dict(ISSUE, rule="δύο"),
        {k: v for k, v in ISSUE.items() if k != "fix"},  # λείπει υποχρεωτικό πεδίο
        dict(ISSUE, reason="   "),
        dict(ISSUE, sentence=42),
    ],
)
def test_strict_schema_rejects_the_whole_reply(bad):
    assert CR.parse_review(_reply(ISSUE, bad)) is None


def test_rule_six_is_valid_for_the_client_document():
    issues = CR.parse_review(_reply(dict(ISSUE, rule=6)), CR.KIND_REWRITE)
    assert issues and issues[0].rule == "6"


# --- v19.3: τα τρία κενά της αξιολόγησης ----------------------------------------
DIAGNOSIS = dict(ISSUE, sentence="Ο Δίας μπορεί να δείχνει ζεστή παρουσία.", rule=1, reason="διάγνωση")
GHOST = dict(ISSUE, sentence="Μια πρόταση που δεν υπάρχει πουθενά στο κείμενο.")


def test_recheck_never_drops_a_severe_issue_that_was_found_in_the_text():
    # 1ος έλεγχος: ένα επιβεβαιωμένο σοβαρό + ένα αμφίβολο · επανέλεγχος: κενή λίστα
    calls = []
    r = _wrapped([_reply(DIAGNOSIS, GHOST), _reply()], calls=calls)(TEXT)
    assert len(calls) == 2
    assert not r.ok and [i.sentence for i in r.blocking_issues] == [DIAGNOSIS["sentence"]]


def test_failed_recheck_keeps_every_issue_and_blocks():
    r = _wrapped([_reply(DIAGNOSIS, GHOST), "όχι json", "όχι json", "όχι json"])(TEXT)
    assert not r.ok and len(r.blocking_issues) == 2


def test_every_issue_is_examined_even_beyond_fifteen():
    mild = [dict(ISSUE, severity="ήπιο", sentence="Ο Δίας μπορεί να δείχνει ζεστή παρουσία.")] * 15
    r = _wrapped([_reply(*mild, ISSUE)])(TEXT)
    assert not r.ok and r.blocking_issues[0].sentence == ISSUE["sentence"]


def test_absurdly_long_reply_is_rejected_and_asked_again():
    many = [dict(ISSUE, severity="ήπιο")] * (CR.MAX_ISSUES_ACCEPTED + 1)
    assert CR.parse_review(_reply(*many)) is None


def test_cost_limit_is_checked_before_every_review_call():
    usage = G.Usage(model="claude-opus-5-5")
    # κάθε έλεγχος: 0,2 M tokens εισόδου + 0,02 M εξόδου με Sonnet = 0,60 $
    review = CR.with_content_review(
        lambda t: Fake(True),
        lambda k, p, m: G.ModelText.build("όχι json", 200_000, 20_000),
        "k", "claude-sonnet-5-5", CR.KIND_ANALYSIS, usage=usage, max_cost_usd=1.0,
    )
    r = review(TEXT)
    assert not r.ok and r.budget_exhausted
    assert usage.spent_usd <= 1.0 and usage.review_requests == 1  # η 2η κλήση (1,20 $) δεν έγινε


def test_full_loop_never_passes_the_cost_limit_and_reports_it():
    usage = G.Usage(model="claude-opus-5-5")
    review = CR.with_content_review(
        lambda t: Fake(True),
        lambda k, p, m: G.ModelText.build(_reply(ISSUE), 100_000, 20_000),
        "k", "claude-sonnet-5-5", CR.KIND_ANALYSIS, usage=usage, max_cost_usd=1.0,
    )
    out = G.generate_validated(
        "k", "Ε", review, model="claude-opus-5-5", usage=usage, max_cost_usd=1.0, max_rounds=0,
        complete=lambda k, t, m: G.ModelText.build(TEXT, 10_000, 10_000),
    )
    assert not out.ok and out.stop_reason == G.STOP_BUDGET and usage.spent_usd <= 1.0


def test_loop_stops_without_revising_when_the_review_cannot_complete():
    calls = []
    review = CR.with_content_review(
        lambda t: Fake(True), lambda k, p, m: "όχι json", "k", "rev", CR.KIND_ANALYSIS
    )
    out = G.generate_validated("k", "Ε", review, complete=lambda k, t, m: calls.append(t) or "κείμενο")
    assert not out.ok and out.stop_reason == G.STOP_REVIEW and len(calls) == 1
    assert out.text == "κείμενο"  # το κείμενο κρατιέται, αλλά ΔΕΝ περνά ως ελεγμένο


def test_rewrite_review_receives_the_source_and_checks_omissions_against_it():
    calls = []
    source = "1ος Οίκος\nΗ ευαισθησία μετατρέπεται σε κατανόηση."
    omission = dict(ISSUE, sentence="Η ευαισθησία μετατρέπεται σε κατανόηση.", rule=6)
    review = CR.with_content_review(
        lambda t: Fake(True), lambda k, p, m: calls.append(p) or _reply(omission), "k", "rev", CR.KIND_REWRITE, source
    )
    r = review("1ος Οίκος\nΆλλο κείμενο.")
    assert not r.ok and "ΠΗΓΗ" in calls[0] and source.splitlines()[1] in calls[0]


def test_review_usage_is_counted_with_the_review_model_price():
    usage = G.Usage(model="claude-opus-5-5")
    review = CR.with_content_review(
        lambda t: Fake(True),
        lambda k, p, m: G.ModelText.build(_reply(), 100_000, 10_000),
        "k", "claude-sonnet-5-5", CR.KIND_ANALYSIS, usage=usage,
    )
    review(TEXT)
    # Sonnet 5.5: 0,1 M × 2 $ + 0,01 M × 10 $ = 0,30 $ · δεν μετρά ως αίτημα δημιουργίας
    assert abs(usage.spent_usd - 0.30) < 1e-9 and usage.main_requests == 0


def test_pipeline_corrects_a_content_issue_until_it_passes():
    answers = iter(["κείμενο Θα αποκτήσεις μεγάλη περιουσία.", "κείμενο Μπορεί να χτίζεις ασφάλεια.", "έντυπο"])
    prompts = []

    def reviewer(k, p, m):
        body = p.split("=== ΚΕΙΜΕΝΟ ΠΡΟΣ ΕΛΕΓΧΟ ===")[-1]
        return _reply(ISSUE) if "Θα αποκτήσεις" in body else _reply()

    result = run_full_pipeline(
        chart=CHART, personal={"Όνομα": "A."}, language="Ελληνικά", instructions_text="ο", style_text="υ",
        instructions_name="v6", style_name="υ", rewrite_command_text=COMMAND, api_key="k", provider="Claude",
        model="m", complete=lambda k, t, m: prompts.append(t) or next(answers),
        validate_analysis_fn=lambda c, t, p: Fake(True), validate_rewrite_fn=lambda c, a, t, p: Fake(True),
        review_complete=reviewer,
    )
    assert result.ok and "Μπορεί να χτίζεις" in result.analysis_text
    assert "Θα αποκτήσεις μεγάλη περιουσία" in prompts[1]  # το εύρημα στάλθηκε για διόρθωση


# --- 3. Επανάληψη στην τεχνική ανάλυση ---------------------------------------
GENERIC = (
    "Αυτός ο Οίκος μπορεί να δείχνει μια βαθιά ανάγκη για ισορροπία ανάμεσα στην προσωπική έκφραση και στις "
    "απαιτήσεις του περιβάλλοντος, με την ωριμότητα να έρχεται σταδιακά μέσα από την εμπειρία. Στην ώριμη "
    "έκφρασή του, ενδέχεται να φέρνει σταθερότητα, κατανόηση και εσωτερική δύναμη. "
) * 4


@pytest.mark.substance
def test_same_generic_paragraph_in_every_house_is_rejected():
    segments = {n: f"{n}ος Οίκος — Θέμα\n{GENERIC}" for n in range(1, 13)}
    blocking = S.repeated_analysis_text(segments)
    assert blocking and blocking[0][0] == list(range(1, 13))


@pytest.mark.substance
def test_one_shared_sentence_between_two_houses_is_allowed():
    own = "Η θέση αυτή μπορεί να δείχνει κάτι διαφορετικό για τον Οίκο {n}, με δική του χροιά και δικό του ρυθμό. "
    shared = "Το τρίγωνο Ήλιος–Δίας, κανονική όψη, μπορεί να υποστηρίζει μια φυσική αισιοδοξία και εμπιστοσύνη."
    segments = {n: f"{n}ος Οίκος\n" + (own.replace("{n}", str(n)) * 3) + (shared if n in (1, 9) else "") for n in range(1, 13)}
    assert S.repeated_analysis_text(segments) == []


def test_referral_to_a_doctor_is_not_a_diagnosis():
    assert S.unsafe_claims("Αν σε απασχολεί η κατάθλιψη, μίλησε με γιατρό.") == []
    assert S.unsafe_claims("Έχεις κατάθλιψη, μίλησε με γιατρό.")


# --- 4. Κόστος -------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,priced",
    [("claude-opus-5-5", True), ("claude-sonnet-5-5", True), ("gpt-5.4", True), ("gpt-5.4-mini", False),
     ("gpt-5.4-pro", False), ("claude-opus-5-5-20260601", True), ("άγνωστο", False)],
)
def test_price_matches_only_the_exact_model(model, priced):
    assert (G.price_for(model) is not None) == priced


def test_price_override_for_an_unknown_model():
    u = G.Usage(model="άγνωστο", price_override=(1.0, 5.0))
    u.add(G.ModelText.build("x", 1_000_000, 100_000))
    assert abs(u.cost_usd - 1.5) < 1e-9


def test_truncated_answer_is_still_counted():
    usage = G.Usage(model="claude-opus-5-5")
    calls = {"n": 0}

    def complete(k, t, m):
        calls["n"] += 1
        if calls["n"] == 1:
            return G.ModelText.build("ΛΑΘΟΣ", 10_000, 1_000)
        if calls["n"] == 2:
            exc = G.TruncatedOutput("κόπηκε")
            exc.input_tokens, exc.output_tokens = 10_000, 100_000
            raise exc
        return G.ModelText.build("σωστό", 10_000, 1_000)

    def validate(t):
        return Fake("ΛΑΘΟΣ" not in t, ["ΛΑΘΟΣ"] if "ΛΑΘΟΣ" in t else [])

    out = G.generate_validated("k", "Ε", validate, model="claude-opus-5-5", complete=complete, usage=usage)
    assert out.ok and usage.requests == 3 and usage.output_tokens == 102_000


def test_cost_limit_is_checked_before_the_first_call():
    calls = []
    with pytest.raises(G.PermanentAPIError) as info:
        G.generate_validated(
            "k", "Ε" * 1000, lambda t: Fake(True), model="claude-opus-5-5", max_cost_usd=0.01,
            complete=lambda k, t, m: calls.append(t) or "x",
        )
    assert calls == [] and "όριο κόστους" in str(info.value)


def test_cost_meter_survives_reloading_the_same_pdf():
    # v19.6: ο μετρητής δένεται με τον χάρτη (όχι με την κατάσταση της περίπτωσης),
    # ώστε το ξαναδιάβασμα του ίδιου PDF να μην τον μηδενίζει.
    assert "case_usage" not in CASE_STATE_KEYS


def test_meter_is_shared_across_stages_and_runs():
    usage = G.Usage(model="claude-opus-5-5")
    for _ in range(2):
        G.generate_validated(
            "k", "Ε", lambda t: Fake(True), model="claude-opus-5-5", usage=usage,
            complete=lambda k, t, m: G.ModelText.build("x", 100_000, 0),
        )
    assert usage.requests == 2 and abs(usage.spent_usd - 0.8) < 1e-9


# --- v19.1: πλαίσιο Οίκων από το βιβλίο μέσα στις οδηγίες (έκδοση 7) ---------


def test_builtin_instructions_contain_the_book_framework_and_it_is_not_duplicated(chart2):
    from pathlib import Path

    from prompts import build_master_prompt
    from reference_loader import docx_text, load_default_references

    instructions, style = load_default_references()
    assert "Θεματικό πλαίσιο και όρια των 12 Οίκων" in instructions
    prompt = build_master_prompt(chart2, {"Όνομα": "A."}, "Ελληνικά", instructions, style, "v7", "ύφος")
    assert "ΠΛΑΙΣΙΟ ΕΡΜΗΝΕΙΑΣ ΑΝΑ ΟΙΚΟ (v19" not in prompt  # μόνο το πλαίσιο των οδηγιών

    command = docx_text((Path(__file__).parent / "Desmeftiki_Entoli_Telikis_Anadiatyposis_v9.docx").read_bytes())
    rewrite = G.build_rewrite_prompt(command, "1ος Οίκος\nκείμενο", "A.", "")
    assert "Συμπληρωματικό πλαίσιο Οίκων" in rewrite and "=== ΠΛΑΙΣΙΟ ΟΙΚΩΝ ===" not in rewrite


def test_reviewer_always_has_the_house_limits():
    assert "ΠΛΑΙΣΙΟ ΕΡΜΗΝΕΙΑΣ ΑΝΑ ΟΙΚΟ" in CR.build_review_prompt("κείμενο")
    assert "προηγούμενες ζωές" in framework_block() and "σεξουαλικού προσανατολισμού" in framework_block()
