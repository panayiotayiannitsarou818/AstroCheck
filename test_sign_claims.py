"""Δηλώσεις «σημείο στο ζώδιο Χ»: λάθος ζώδιο εντοπίζεται, ενώ συνηθισμένες
διατυπώσεις που ΔΕΝ είναι θέση (Θεωρία Μοιρών, κυβερνήτες, Πυθμένας Ουρανού,
άλλος πλανήτης στην ίδια πρόταση) δεν δίνουν ψευδή σφάλματα."""
from pathlib import Path

import pytest

import validator as V
from parser import parse_astrodienst_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"   # Σελήνη Παρθένος, Άρης Ζυγός


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


@pytest.mark.parametrize("text,expected", [
    ("Η Σελήνη στον Σκορπιό μπορεί να δείχνει ένταση.", [("Σελήνη", "Σκορπιός", "Παρθένος")]),
    ("Ο Άρης, στον Κριό, δείχνει ορμή.", [("Άρης", "Κριός", "Ζυγός")]),
    ("Ο Ωροσκόπος στον Λέοντα.", [("Ωροσκόπος", "Λέων", "Τοξότης")]),
    ("Ο Ερμής στους Ιχθύες.", [("Ερμής", "Ιχθύες", "Υδροχόος")]),
])
def test_wrong_sign_is_caught(chart, text, expected):
    assert [e[:3] for e in V._sign_claim_errors(chart, text)] == expected


@pytest.mark.parametrize("text", [
    "Ο Ήλιος στον Υδροχόο δείχνει ανεξαρτησία.",
    "Ο Άρης, στον Ζυγό, δείχνει διπλωματία.",
    "Ο Βόρειος Δεσμός στον Καρκίνο κυβερνάται από τη Σελήνη, η οποία βρίσκεται στην Παρθένο.",
    "Ο Ποσειδώνας, λόγω μοίρας, αντιστοιχεί στον Ταύρο.",
    "Ο Πυθμένας Ουρανού στους Ιχθύες.",
    "Ο Κρόνος σχηματίζει τετράγωνο με τον Δία στον Σκορπιό.",
    "Η Αφροδίτη, κυβερνήτρια του Οίκου, είναι ο κυβερνήτης που αντιστοιχεί στον Ταύρο.",
])
def test_non_placement_phrases_do_not_trigger(chart, text):
    assert V._sign_claim_errors(chart, text) == []


def test_ic_is_not_uranus_for_house_claims(chart):
    assert V._location_claim_errors(chart, "Ο Πυθμένας Ουρανού βρίσκεται στον 4ο Οίκο.") == []


def test_wrong_sign_fails_the_client_document(chart):
    houses = "\n".join(f"{n}ος Οίκος\nΚείμενο." for n in range(1, 13))
    rewrite = f"{houses}\nΗ Σελήνη στον Σκορπιό σε κάνει έντονη."
    result = V.validate_rewrite(chart, houses, rewrite)
    assert not result.ok and result.wrong_sign_claims
    assert any("Λανθασμένο ζώδιο — Σελήνη" in line for line in result.details_lines())
