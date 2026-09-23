"""
test_parser.py
===============
Πρώτο test με πραγματικό Astrodienst PDF (βλ. README «Γνωστό κενό»): μέχρι
τώρα το parser.py δεν καλυπτόταν καθόλου από tests, ενώ βασίζεται σε
hardcoded pixel συντεταγμένες πάνω στη σελίδα -- μια αλλαγή στη διάταξη/
γραμματοσειρά ενός μελλοντικού Astrodienst export (ή ένα ατυχές μελλοντικό
επεξεργασία του ίδιου του parser.py) θα το έσπαγε σιωπηλά.

Το fixture (tests/fixtures/astro_paradeigma.pdf) είναι το δημόσιο
παράδειγμα "Paradeigma" του ίδιου του Astrodienst -- όχι πραγματικά
δεδομένα πελάτη -- οπότε μπαίνει με ασφάλεια στο repository.

Σημείωση για συντηρητές: το PDF έχει δύο στήλες δίπλα-δίπλα στην ίδια
σελίδα (πλανήτες αριστερά, ακμές Οίκων δεξιά), ευθυγραμμισμένες ανά γραμμή.
Η γραμμή του Mean Node ("K", βλ. parser.wanted) ευθυγραμμίζεται με τη
γραμμή της 11ης ακμής Οίκου -- αν αφαιρεθεί το "K" από το wanted, η 11η
ακμή χάνεται σιωπηλά, όπως επιβεβαιώθηκε χειροκίνητα κατά τη δημιουργία
αυτού του αρχείου. Το test_all_twelve_cusps_present παρακάτω αρκεί για να
πιάσει μια τέτοια παλινδρόμηση χωρίς να χρειάζεται ξεχωριστό test.
"""
from __future__ import annotations
from pathlib import Path

import pytest

from parser import parse_astrodienst_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma.pdf"


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


def test_no_warnings(chart):
    assert chart.warnings == []


def test_metadata(chart):
    assert chart.name == "Paradeigma"
    assert chart.date == "Th., 27 January 1983"
    assert chart.time == "5:00 a.m."
    assert chart.place == "Dháli, CYP, 33e25, 35n01"
    assert chart.house_system == "Placidus"


def test_counts(chart):
    # 13 σειρές πλανητών/σημείων στο PDF, μείον Mean Node (δεν
    # ενσωματώνεται στο Chart), συν Ωροσκόπος, Μεσουράνημα και ο
    # μαθηματικά παραγόμενος Νότιος Δεσμός.
    assert len(chart.points) == 15
    assert len(chart.cusps) == 12
    assert len(chart.aspects) == 38


def test_all_twelve_cusps_present(chart):
    numbers = sorted(int(c.name.split("ος")[0]) for c in chart.cusps)
    assert numbers == list(range(1, 13))


def test_sun_position_and_house(chart):
    sun = next(p for p in chart.points if p.name == "Ήλιος")
    assert (sun.sign, sun.degree, sun.minute, sun.second) == ("Υδροχόος", 6, 35, 54)
    assert sun.house == 1


def test_retrograde_flags(chart):
    # Η ανάδρομη κίνηση διαπιστώνεται από την αρνητική ημερήσια ταχύτητα
    # στο PDF, όχι μόνο από τον χαρακτήρα στάσης "(" -- βλ. σχόλιο στο
    # parser._parse_positions.
    by_name = {p.name: p for p in chart.points}
    assert by_name["Ερμής"].retrograde is True
    assert by_name["Χείρωνας"].retrograde is True
    assert by_name["Σελήνη"].retrograde is False
    assert by_name["Ήλιος"].retrograde is False


def test_south_node_is_derived_mathematically(chart):
    south = next(p for p in chart.points if p.name == "Νότιος Δεσμός")
    north = next(p for p in chart.points if p.name == "Βόρειος Δεσμός")
    assert abs((south.absolute - north.absolute) % 360 - 180) < 0.01
    assert south.retrograde == north.retrograde


def test_known_hard_aspect(chart):
    hard = {
        (a.first, a.second): a
        for a in chart.aspects
        if a.aspect in ("Τετράγωνο", "Αντίθεση")
    }
    assert ("Άρης", "Ουρανός") in hard
    assert hard[("Άρης", "Ουρανός")].orb_text == "0°39′"
    assert hard[("Άρης", "Ουρανός")].weight == "Στενή/ισχυρή"


def test_angle_conjunction_detected(chart):
    # Κανόνας 6Β/OPPOSITE_ANGLE: μια σύνοδος με τον Ωροσκόπο ή το
    # Μεσουράνημα πρέπει να ξεχωρίζει, ώστε ο validator να μπορεί να την
    # απαιτήσει υποχρεωτικά.
    angle_conjunctions = [
        a for a in chart.aspects
        if a.aspect == "Σύνοδος"
        and (a.first in ("Ωροσκόπος", "Μεσουράνημα") or a.second in ("Ωροσκόπος", "Μεσουράνημα"))
    ]
    assert len(angle_conjunctions) >= 1
