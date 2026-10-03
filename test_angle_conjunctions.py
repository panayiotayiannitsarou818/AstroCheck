"""
test_angle_conjunctions.py
===========================
Κανόνας 6Β: σύνοδος με Ωροσκόπο/Μεσουράνημα που ΛΕΙΠΕΙ από τον πίνακα του
Astrodienst αλλά προκύπτει από τις θέσεις πρέπει να προστίθεται από την
Python (όχι από το LLM), με σαφή ένδειξη προέλευσης.

Σημείωση: κανένα από τα 6 fixtures δεν έχει τέτοια περίπτωση (ο πίνακας
καλύπτει ήδη συνόδους έως ~8°), γι' αυτό το βασικό test χρησιμοποιεί
συνθετικές θέσεις. Τα fixtures χρησιμοποιούνται για να επιβεβαιωθεί ότι
ΔΕΝ δημιουργούνται διπλότυπα και ότι τα 10,35°/10,8° μένουν εκτός ορίου.
"""

from __future__ import annotations
from pathlib import Path

import pytest

from astrology import (
    ANGLE_CONJUNCTION_MAX_ORB,
    POSITION_DERIVED_SOURCE,
    angle_conjunctions_from_positions,
)
from models import Aspect, Chart, Point
from parser import parse_astrodienst_pdf
from validation_aspects import _mandatory_aspects

FIXTURES = Path(__file__).parent / "fixtures"


def _pt(name, absolute, kind="planet"):
    return Point("x", name, "", 0, 0, 0, absolute, kind=kind)


def _synthetic_points():
    return [
        _pt("Ωροσκόπος", 100.0, "angle"),
        _pt("Μεσουράνημα", 10.0, "angle"),
        _pt("Ερμής", 109.0),     # 9°00′ από Ωροσκόπο -> λείπει, πρέπει να προστεθεί
        _pt("Αφροδίτη", 95.0),   # 5°00′ από Ωροσκόπο -> υπάρχει ήδη στον πίνακα
        _pt("Κρόνος", 20.5),     # 10°30′ από Μεσουράνημα -> εκτός ορίου
        _pt("Δίας", 1.0),        # 9°00′ από Μεσουράνημα, πέρα από 0° Κριού
    ]


def _grid():
    return [Aspect("Αφροδίτη", "Ωροσκόπος", "Σύνοδος", 5.0, "5°00′", "Πλατιά αλλά έγκυρη", "Πίνακας Astrodienst")]


def test_missing_conjunction_is_added_from_positions():
    added = angle_conjunctions_from_positions(_synthetic_points(), _grid())
    pairs = {(a.first, a.second): a for a in added}
    assert ("Ερμής", "Ωροσκόπος") in pairs
    mercury = pairs[("Ερμής", "Ωροσκόπος")]
    assert mercury.aspect == "Σύνοδος"
    assert mercury.orb_text == "9°00′"
    assert mercury.weight == "Πολύ πλατιά/δευτερεύουσα"
    assert mercury.source == POSITION_DERIVED_SOURCE


def test_wraparound_at_zero_aries():
    added = angle_conjunctions_from_positions(_synthetic_points(), _grid())
    assert any(a.first == "Δίας" and a.second == "Μεσουράνημα" and a.orb_text == "9°00′" for a in added)


def test_existing_grid_conjunction_not_duplicated():
    added = angle_conjunctions_from_positions(_synthetic_points(), _grid())
    assert not any(a.first == "Αφροδίτη" for a in added)


def test_beyond_limit_not_added():
    added = angle_conjunctions_from_positions(_synthetic_points(), _grid())
    assert not any(a.first == "Κρόνος" for a in added)
    assert ANGLE_CONJUNCTION_MAX_ORB == 10.0


def test_computed_conjunctions_are_mandatory_like_grid_ones():
    """Η προέλευση δεν καθορίζει την υποχρέωση (κανόνας 6Β): σύνοδος με γωνία
    στις 9° είναι υποχρεωτική ανά Οίκο, όπως και του πίνακα στις 8°03′."""
    chart = Chart(points=_synthetic_points(), aspects=_grid())
    chart.aspects += angle_conjunctions_from_positions(chart.points, chart.aspects)
    mandatory = _mandatory_aspects(chart)
    assert any(a.first == "Αφροδίτη" for a in mandatory)
    assert any(a.first == "Ερμής" and a.source == POSITION_DERIVED_SOURCE for a in mandatory)


@pytest.mark.parametrize("pdf", sorted(FIXTURES.glob("*.pdf")), ids=lambda p: p.name)
def test_fixtures_no_duplicates_and_no_false_additions(pdf):
    chart = parse_astrodienst_pdf(pdf.read_bytes(), pdf.name)
    conj = [
        frozenset((a.first, a.second))
        for a in chart.aspects
        if a.aspect == "Σύνοδος" and {a.first, a.second} & {"Ωροσκόπος", "Μεσουράνημα"}
    ]
    assert len(conj) == len(set(conj))
    # Στα πραγματικά fixtures ο πίνακας καλύπτει ήδη τα πάντα έως 10°·
    # τα Ερμής–Ωροσκόπος (10,35°) και Ουρανός–Μεσουράνημα (10,8°) μένουν εκτός.
    assert not any(a.source == POSITION_DERIVED_SOURCE for a in chart.aspects)
