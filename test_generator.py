"""Ο αυτόματος κύκλος διόρθωσης, χωρίς πραγματική κλήση στο OpenAI."""

from dataclasses import dataclass, field

from generator import generate_validated, revision_prompt


@dataclass
class FakeResult:
    ok: bool
    errors: list = field(default_factory=list)

    def summary(self):
        return "ok" if self.ok else f"{len(self.errors)} σφάλματα"

    def details_lines(self):
        return list(self.errors)


def _validator(bad_words):
    def validate(text):
        errs = [f"βρέθηκε «{w}»" for w in bad_words if w in text]
        return FakeResult(not errs, errs)

    return validate


def test_passes_first_time_with_one_call():
    calls = []
    out = generate_validated(
        "k",
        "ΕΝΤΟΛΗ",
        _validator(["ΛΑΘΟΣ"]),
        complete=lambda k, t, m: calls.append(t) or "σωστό κείμενο",
    )
    assert out.ok and len(calls) == 1 and len(out.rounds) == 1


def test_errors_are_sent_back_and_fixed():
    sent = []
    answers = iter(["κείμενο με ΛΑΘΟΣ", "διορθωμένο κείμενο"])
    out = generate_validated(
        "k",
        "ΕΝΤΟΛΗ",
        _validator(["ΛΑΘΟΣ"]),
        complete=lambda k, t, m: sent.append(t) or next(answers),
    )
    assert out.ok and out.text == "διορθωμένο κείμενο"
    assert [r.kind for r in out.rounds] == ["δημιουργία", "διόρθωση"]
    # ο 2ος γύρος περιέχει τα σφάλματα, την εντολή και την προηγούμενη ανάλυση
    assert "βρέθηκε «ΛΑΘΟΣ»" in sent[1] and "ΕΝΤΟΛΗ" in sent[1] and "κείμενο με ΛΑΘΟΣ" in sent[1]


def test_stops_after_max_rounds_and_keeps_best_attempt():
    answers = iter(["Α Β Γ", "Α", "Α Β"])  # 3, 1, 2 σφάλματα
    out = generate_validated(
        "k", "Ε", _validator(["Α", "Β", "Γ"]), max_rounds=3, complete=lambda k, t, m: next(answers)
    )
    assert not out.ok and len(out.rounds) == 3
    assert out.text == "Α" and out.rounds[1].error_count == 1


def test_revision_prompt_survives_braces():
    text = revision_prompt("εντολή {x}", "ανάλυση {y}", ["σφάλμα {z}"])
    assert "{x}" in text and "{y}" in text and "{z}" in text


# --- v16: «μέχρι να εγκριθεί» ----------------------------------------------
from generator import DEFAULT_MAX_ROUNDS, MAX_ROUNDS_LIMIT, max_rounds_from


def test_default_keeps_correcting_beyond_three_rounds_until_approved():
    # 5 απορρίψεις και έγκριση στον 6ο γύρο: με την προεπιλογή ο κύκλος δεν σταματά στους 3.
    answers = iter(["ΛΑΘΟΣ"] * 5 + ["σωστό"])
    out = generate_validated("k", "Ε", _validator(["ΛΑΘΟΣ"]), complete=lambda k, t, m: next(answers))
    assert out.ok and len(out.rounds) == 6 and out.text == "σωστό"
    assert DEFAULT_MAX_ROUNDS >= 6


def test_safety_cap_stops_a_loop_that_never_passes():
    calls = []
    out = generate_validated(
        "k", "Ε", _validator(["ΛΑΘΟΣ"]), max_rounds=4, complete=lambda k, t, m: calls.append(t) or "ΛΑΘΟΣ"
    )
    assert not out.ok and len(calls) == 4


def test_a_failed_request_during_correction_does_not_stop_the_loop():
    state = {"n": 0}

    def complete(k, t, m):
        state["n"] += 1
        if state["n"] == 1:
            return "ΛΑΘΟΣ"
        if state["n"] == 2:
            raise TimeoutError("δίκτυο")
        return "σωστό"

    out = generate_validated("k", "Ε", _validator(["ΛΑΘΟΣ"]), complete=complete)
    assert out.ok and out.text == "σωστό"
    assert "απέτυχε" in out.rounds[1].summary and len(out.rounds) == 3


def test_max_rounds_setting_is_parsed_and_clamped():
    assert max_rounds_from("15") == 15
    assert max_rounds_from(0) == 0  # 0 = χωρίς όριο
    assert max_rounds_from(999) == MAX_ROUNDS_LIMIT
    assert max_rounds_from("όχι αριθμός") == DEFAULT_MAX_ROUNDS
    assert max_rounds_from(None) == DEFAULT_MAX_ROUNDS


def test_unlimited_mode_keeps_going_until_approved():
    answers = iter(["ΛΑΘΟΣ"] * 40 + ["σωστό"])
    out = generate_validated("k", "Ε", _validator(["ΛΑΘΟΣ"]), max_rounds=0, complete=lambda k, t, m: next(answers))
    assert out.ok and len(out.rounds) == 41
