"""v18: ασφαλής γλώσσα, ουσιαστικό περιεχόμενο, όρια διακοπής, κατανάλωση,
καθαρισμός κατάστασης."""

import pytest

import generator as G
import validation_safety as S
import validator as V
from case_state import CASE_STATE_KEYS, reset_case_state
from test_english import build_analysis, chart2  # noqa: F401 (fixture)
from test_rewrite_client import SOURCE, _chart as _rw_chart, _rewrite

# --- 1. Ασφαλής γλώσσα --------------------------------------------------------
UNSAFE = [
    "Έχεις κατάθλιψη και χρειάζεσαι ψυχιατρική θεραπεία.",
    "Πάσχεις από διαταραχή άγχους.",
    "Η διάγνωση είναι σαφής: έχεις διπολική.",
    "Θα πετύχεις σίγουρα ως χειρουργός.",
    "Ο γάμος σου θα αποτύχει.",
    "Αναπόφευκτα θα χωρίσεις.",
    "Θα αρρωστήσεις μετά τα σαράντα.",
    "Είσαι προορισμένη να μείνεις μόνη.",
    "Είναι γραφτό σου να ηγηθείς.",
    "Πρέπει να γίνεις δικηγόρος.",
    "Το ιδανικό επάγγελμα για σένα είναι η ιατρική.",
    "Δεν είσαι κατάλληλη για ηγετικό ρόλο.",
    "You have depression.",
    "You will definitely succeed as a surgeon.",
    "Your marriage will fail.",
    "You are destined to lead.",
    "The right career for you is law.",
    "You are not suited for management.",
]
SAFE = [
    "Συμβολικό πλαίσιο αυτοπαρατήρησης — όχι επιστημονική διάγνωση, απόδειξη χαρακτήρα ή βεβαιότητα γεγονότων.",
    "Ο Χείρωνας περιγράφεται ως «πληγή»· πρόκειται για συμβολισμό και όχι για ψυχολογική διάγνωση.",
    "Αν κάποιο θέμα προκαλεί δυσφορία, μπορεί να είναι χρήσιμη η συζήτηση με κατάλληλο επαγγελματία ψυχικής υγείας.",
    "Ο Δίας στον Καρκίνο μπορεί να δείχνει φροντίδα και προστασία.",
    "Μπορεί να πετύχεις περισσότερα όταν δουλεύεις με συνέπεια.",
    "Σίγουρα αξίζει να δοθεί χρόνος στην ξεκούραση.",
    "Βέβαια, θα χρειαστεί υπομονή.",
    "Ο όγκος της δουλειάς ίσως σε κουράζει.",
    "Δεν προτείνεται τομέας ή επάγγελμα υγείας.",
    "Γλωσσικός έλεγχος για απόλυτες ή διαγνωστικές διατυπώσεις.",
    "This is a symbolic framework, not a diagnosis.",
    "The Moon in Cancer may point to a caring nature.",
]


@pytest.mark.parametrize("sentence", UNSAFE)
def test_unsafe_sentence_is_caught(sentence):
    assert S.unsafe_claims(sentence), sentence


@pytest.mark.parametrize("sentence", SAFE)
def test_safe_sentence_is_not_flagged(sentence):
    assert S.unsafe_claims(sentence) == []


def test_unsafe_sentence_blocks_the_client_document():
    assert V.validate_rewrite(_rw_chart(), SOURCE, _rewrite()).ok
    r = V.validate_rewrite(_rw_chart(), SOURCE, _rewrite(" Ο γάμος σου θα αποτύχει."))
    assert not r.ok and r.unsafe_claims
    assert "μη ασφαλείς διατυπώσεις" in r.summary()
    assert any("Ο γάμος σου θα αποτύχει" in line for line in r.details_lines())


def test_unsafe_sentence_blocks_the_analysis(chart2):
    good = build_analysis(chart2, "el")
    assert V.validate_analysis(chart2, good).ok
    bad = good.replace("\n2ος Οίκος", "\nΈχεις κατάθλιψη και χρειάζεσαι ψυχιατρική θεραπεία.\n2ος Οίκος", 1)
    r = V.validate_analysis(chart2, bad)
    assert not r.ok and r.unsafe_claims


def test_success_message_names_the_checks_instead_of_approval():
    r = V.validate_rewrite(_rw_chart(), SOURCE, _rewrite())
    assert "Πέρασε τους ελέγχους δεδομένων, δομής και ασφαλούς γλώσσας" in r.summary()


# --- 2. Ουσιαστικό περιεχόμενο -------------------------------------------------
PROSE = (
    "Η θέση αυτή μπορεί να δείχνει μια τάση για φροντίδα, σταθερότητα και ουσιαστική επαφή με τους "
    "ανθρώπους γύρω σου, με έμφαση στη συνέπεια και στην υπομονή μέσα στον χρόνο. "
)


def _segment(prose_repeats=8, strength="Ζεστή παρουσία που δημιουργεί εμπιστοσύνη στους γύρω σου."):
    return (
        "1ος Οίκος — Ταυτότητα\n"
        "Σελήνη–Δίας Αντίθεση (orb 0°12′, Στενή/ισχυρή)\n"
        + PROSE * prose_repeats
        + "\nΠλαίσιο σύνοψης\n"
        f"Βασική δύναμη: {strength}\n"
        "Κυβερνήτης: Ερμής\n"
    )


@pytest.mark.substance
def test_full_house_has_substance():
    assert S.thin_analysis_content({1: _segment()}) == []


@pytest.mark.substance
@pytest.mark.parametrize("value", ["κείμενο", "…", "[συμπληρώνεται]", "Καλή", "TBD"])
def test_placeholder_summary_line_is_rejected(value):
    problems = S.thin_analysis_content({1: _segment(strength=value)})
    assert any("Βασική δύναμη" in what for _, what in problems)


@pytest.mark.substance
def test_house_with_almost_no_interpretation_is_rejected():
    problems = S.thin_analysis_content({1: _segment(prose_repeats=1)})
    assert any("λέξεις ερμηνευτικού κειμένου" in what for _, what in problems)


@pytest.mark.substance
def test_skeleton_analysis_fails_when_the_substance_check_is_on(chart2):
    r = V.validate_analysis(chart2, build_analysis(chart2, "el"))
    assert not r.ok and r.thin_content
    assert "χωρίς ουσιαστικό περιεχόμενο" in r.summary()


# --- 3. Καθαρισμός κατάστασης ------------------------------------------------
class _State(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


def test_new_analysis_clears_the_previous_automatic_result():
    assert "auto_result" in CASE_STATE_KEYS
    state = _State(auto_result={"ok": True, "name": "X.Y."})
    reset_case_state(state)
    assert "auto_result" not in state


# --- 4. Όρια διακοπής και κατανάλωση ----------------------------------------
class _R:
    def __init__(self, ok, errors):
        self.ok, self._errors, self.warnings = ok, errors, []

    def summary(self):
        return "ok" if self.ok else "σφάλματα"

    def details_lines(self):
        return list(self._errors)


def _validate(text):
    return _R("ΛΑΘΟΣ" not in text, [w for w in text.split() if w == "ΛΑΘΟΣ"])


def test_stagnation_stops_the_loop_and_keeps_the_best_attempt():
    calls = []
    out = G.generate_validated(
        "k", "Ε", _validate, max_rounds=0, stall_rounds=3, complete=lambda k, t, m: calls.append(t) or "ΛΑΘΟΣ"
    )
    assert not out.ok and out.stop_reason == G.STOP_STALLED
    assert len(calls) == 4  # 1 δημιουργία + 3 γύροι χωρίς πρόοδο


def test_progress_resets_the_stagnation_counter():
    answers = iter(["ΛΑΘΟΣ ΛΑΘΟΣ ΛΑΘΟΣ", "ΛΑΘΟΣ ΛΑΘΟΣ ΛΑΘΟΣ", "ΛΑΘΟΣ ΛΑΘΟΣ", "ΛΑΘΟΣ ΛΑΘΟΣ", "ΛΑΘΟΣ", "ΛΑΘΟΣ", "σωστό"])
    out = G.generate_validated("k", "Ε", _validate, stall_rounds=2, complete=lambda k, t, m: next(answers))
    assert out.ok and out.text == "σωστό"


class AuthenticationError(Exception):
    status_code = 401


class NotFoundError(Exception):
    status_code = 404


class InternalServerError(Exception):
    status_code = 529


@pytest.mark.parametrize("exc", [AuthenticationError("bad key"), NotFoundError("no model")])
def test_permanent_error_stops_immediately_on_the_first_request(exc):
    calls = []

    def complete(k, t, m):
        calls.append(t)
        raise exc

    with pytest.raises(G.PermanentAPIError):
        G.generate_validated("k", "Ε", _validate, complete=complete)
    assert len(calls) == 1


def test_permanent_error_during_correction_is_not_retried():
    calls = []

    def complete(k, t, m):
        calls.append(t)
        if len(calls) == 1:
            return "ΛΑΘΟΣ"
        raise AuthenticationError("bad key")

    with pytest.raises(G.PermanentAPIError) as info:
        G.generate_validated("k", "Ε", _validate, complete=complete)
    assert len(calls) == 2 and "κλειδί" in str(info.value)


def test_no_credit_is_explained():
    class BadRequestError(Exception):
        status_code = 400

    assert "υπόλοιπο" in G.explain_permanent_error(BadRequestError("Your credit balance is too low"))


def test_repeated_temporary_failures_stop_the_loop():
    calls = []

    def complete(k, t, m):
        calls.append(t)
        if len(calls) == 1:
            return "ΛΑΘΟΣ"
        raise InternalServerError("overloaded")

    out = G.generate_validated("k", "Ε", _validate, max_rounds=0, complete=complete)
    assert out.stop_reason == G.STOP_FAILURES and len(calls) == 1 + G.MAX_CONSECUTIVE_FAILURES


def _priced(text, inp=100_000, outp=50_000):
    return G.ModelText.build(text, inp, outp)


def test_usage_and_cost_are_counted():
    answers = iter([_priced("ΛΑΘΟΣ"), _priced("σωστό")])
    out = G.generate_validated("k", "Ε", _validate, model="claude-opus-5-5", complete=lambda k, t, m: next(answers))
    assert out.ok and out.usage.requests == 2
    assert out.usage.input_tokens == 200_000 and out.usage.output_tokens == 100_000
    # 0,2 M × 4 $ + 0,1 M × 20 $ = 2,80 $
    assert abs(out.usage.cost_usd - 2.8) < 1e-9
    assert "2,80 $" in out.usage.describe()


def test_unknown_model_shows_tokens_without_cost():
    u = G.Usage(model="gpt-x")
    u.add(_priced("x"))
    assert u.cost_usd is None and "tokens" in u.describe() and "€" not in u.describe()


def test_cost_limit_stops_the_loop():
    out = G.generate_validated(
        "k", "Ε", _validate, model="claude-opus-5-5", max_rounds=0, max_cost_usd=5.0,
        complete=lambda k, t, m: _priced("ΛΑΘΟΣ"),
    )
    # v19: κάθε αίτημα 1,40 $ · ο έλεγχος γίνεται ΠΡΙΝ την κλήση: μετά από 3 (4,20 $)
    # το 4ο θα έφτανε τα 5,60 $ > 5 $, άρα δεν στέλνεται.
    assert out.stop_reason == G.STOP_BUDGET and out.usage.requests == 3
    assert out.usage.cost_usd <= 5.0


@pytest.mark.parametrize("value,expected", [("", None), ("0", None), ("abc", None), ("3,5", 3.5), ("10", 10.0)])
def test_cost_limit_setting(value, expected):
    assert G.cost_limit_from(value) == expected


def test_quality_round_does_not_keep_a_much_shorter_text():
    class Q(_R):
        pass

    def validate(text):
        r = Q(True, [])
        r.warnings = ["ΣΗΜ"] * text.count("ΣΗΜ")
        return r

    long_text = "ΣΗΜ " + "λέξη " * 400
    short_text = "λέξη " * 100
    answers = iter([long_text, short_text])
    out = G.generate_validated("k", "Ε", validate, polish=True, complete=lambda k, t, m: next(answers))
    assert out.text == long_text and "συντομότερο" in out.rounds[-1].summary
