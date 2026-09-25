from models import Chart, Point
import validator as V

CLOSING = V._CLOSING_SENTENCE
SOURCE = "\n".join(
    [f"{n}ος Οίκος — Θέμα\nΚείμενο." for n in range(1, 13)]
    + ["Τελική συνθετική εικόνα", "Συμβολική κατεύθυνση εξέλιξης",
       "Προτάσεις προσωπικής ανάπτυξης", "Παράρτημα επιβεβαιωμένων όψεων",
       "Αφροδίτη–Κρόνος Τετράγωνο 1°13′ Στενή/ισχυρή Πίνακας Astrodienst"]
)


def _chart():
    return Chart(points=[Point("x", "Σελήνη", "", 0, 0, 0, 0.0, 10)])


def _rewrite(extra=""):
    return "\n".join(
        [f"{n}ος Οίκος — Θέμα\nΚείμενο για σένα.{extra if n == 2 else ''}" for n in range(1, 13)]
        + ["Τελική συνθετική εικόνα", "Κείμενο.", "Συμβολική κατεύθυνση εξέλιξης", "Κείμενο.",
           "Προτάσεις προσωπικής ανάπτυξης", "Κείμενο.", CLOSING]
    )


def test_clean_client_text_passes_without_appendix():
    r = V.validate_rewrite(_chart(), SOURCE, _rewrite())
    assert r.ok, r.details_lines()


def test_degrees_orb_weight_are_rejected():
    r = V.validate_rewrite(_chart(), SOURCE, _rewrite(" Η Αφροδίτη στις 23°21′ έχει orb 1°13′, Στενή/ισχυρή."))
    cats = {c for c, _ in r.technical_data}
    assert not r.ok
    assert {"μοίρες/λεπτά", "orb", "κατηγορία βαρύτητας"} <= cats


def test_appendix_is_rejected():
    text = _rewrite().replace(CLOSING, "Τεχνικό παράρτημα\nΠίνακας όψεων.\n" + CLOSING)
    r = V.validate_rewrite(_chart(), SOURCE, text)
    assert any(c == "Παράρτημα/πίνακας όψεων" for c, _ in r.technical_data)


def test_missing_closing_sentence_is_rejected():
    r = V.validate_rewrite(_chart(), SOURCE, _rewrite().replace(CLOSING, "Τέλος."))
    assert r.missing_closing_sentence and not r.ok
