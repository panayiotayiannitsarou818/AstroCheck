from models import Chart, Point
import validator as V
from sample_texts import houses_el, section_body

SOURCE = "\n".join(
    [f"{n}ος Οίκος — Θέμα\nΚείμενο." for n in range(1, 13)]
    + [
        "Τελική συνθετική εικόνα",
        "Συμβολική κατεύθυνση εξέλιξης",
        "Προτάσεις προσωπικής ανάπτυξης",
        "Παράρτημα επιβεβαιωμένων όψεων",
        "Αφροδίτη–Κρόνος Τετράγωνο 1°13′ Στενή/ισχυρή Πίνακας Astrodienst",
    ]
)


def _chart():
    return Chart(points=[Point("x", "Σελήνη", "", 0, 0, 0, 0.0, 10)])


def _rewrite(extra=""):
    return "\n".join(
        [houses_el(_chart(), " — Θέμα", {2: extra})]
        + [
            "Τελική συνθετική εικόνα",
            section_body(),
            "Συμβολική κατεύθυνση εξέλιξης",
            section_body(),
            "Προτάσεις προσωπικής ανάπτυξης",
            section_body(),
        ]
    )


def test_clean_client_text_passes_without_appendix():
    r = V.validate_rewrite(_chart(), SOURCE, _rewrite())
    assert r.ok, r.details_lines()


def test_degrees_orb_weight_are_rejected():
    r = V.validate_rewrite(
        _chart(), SOURCE, _rewrite(" Η Αφροδίτη στις 23°21′ έχει orb 1°13′, Στενή/ισχυρή.")
    )
    cats = {c for c, _ in r.technical_data}
    assert not r.ok
    assert {"μοίρες/λεπτά", "orb", "κατηγορία βαρύτητας"} <= cats


def test_appendix_is_rejected():
    text = _rewrite() + "\nΤεχνικό παράρτημα\nΠίνακας όψεων."
    r = V.validate_rewrite(_chart(), SOURCE, text)
    assert any(c == "Παράρτημα/πίνακας όψεων" for c, _ in r.technical_data)


def test_no_closing_sentence_is_required():
    r = V.validate_rewrite(_chart(), SOURCE, _rewrite() + "\nΤέλος.")
    assert r.ok, r.details_lines()


def test_old_mathematical_check_sentence_is_flagged_for_removal():
    old = (
        "Αυτή η ανάλυση βασίζεται σε πλήρη μαθηματικό έλεγχο όλων των αστρολογικών "
        "όψεων του χάρτη σου· τα τεχνικά στοιχεία είναι διαθέσιμα αν θες να τα δεις."
    )
    r = V.validate_rewrite(_chart(), SOURCE, _rewrite() + "\n" + old)
    assert not r.ok
    assert any(c.startswith("πρόταση μαθηματικού ελέγχου") for c, _ in r.technical_data)
