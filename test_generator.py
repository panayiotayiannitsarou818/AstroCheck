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
