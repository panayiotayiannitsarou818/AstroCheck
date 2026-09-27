"""Έλεγχος του parser σε όλα τα ανωνυμοποιημένα PDF-παραδείγματα.

Τα αρχεία στο fixtures/ δεν περιέχουν όνομα (έχει αφαιρεθεί από το PDF)·
ο parser τότε χρησιμοποιεί το όνομα του αρχείου.
"""

from pathlib import Path

import pytest

from parser import integrity_problems, parse_astrodienst_pdf

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("astro_paradeigma*.pdf"))


def _parse(name):
    path = Path(__file__).parent / "fixtures" / name
    return parse_astrodienst_pdf(path.read_bytes(), path.name)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_every_fixture_passes_integrity(path):
    chart = parse_astrodienst_pdf(path.read_bytes(), path.name)
    printed = {p.name: p.house for p in chart.points}
    assert integrity_problems(chart.points, chart.cusps, chart.aspects, printed) == []
    assert len(chart.cusps) == 12 and not chart.warnings


def test_two_page_pdf_with_transits_reads_only_natal_page():
    chart = _parse("astro_paradeigma_2.pdf")
    sun = next(p for p in chart.points if p.name == "Ήλιος")
    assert (sun.sign, sun.degree, sun.minute, sun.second, sun.house) == ("Υδροχόος", 21, 55, 7, 3)
    assert len(chart.aspects) == 39  # 35 του πίνακα + 4 του Νότιου Δεσμού


def test_station_marker_is_not_retrograde():
    chart = _parse("astro_paradeigma_2.pdf")
    retro = {p.name for p in chart.points if p.retrograde}
    assert "Αφροδίτη" not in retro  # «(» = στάση, όχι ανάδρομη
    assert {"Ερμής", "Κρόνος", "Πλούτωνας"} <= retro


def test_name_is_not_in_anonymized_fixture():
    chart = _parse("astro_paradeigma_3.pdf")
    assert chart.name == "astro_paradeigma_3"
    neptune = next(p for p in chart.points if p.name == "Ποσειδώνας")
    assert neptune.retrograde and neptune.house == 7


def test_southern_hemisphere_and_29_degrees():
    chart = _parse("astro_paradeigma_4.pdf")
    assert "20s09" in chart.place  # νότιο ημισφαίριο
    mercury = next(p for p in chart.points if p.name == "Ερμής")
    assert (mercury.sign, mercury.degree, mercury.minute, mercury.house) == ("Λέων", 29, 52, 7)
    neptune = next(p for p in chart.points if p.name == "Ποσειδώνας")
    assert not neptune.retrograde  # «(» με θετική ταχύτητα = στάση
    assert {p.name for p in chart.points if p.retrograde} >= {"Κρόνος", "Χείρωνας"}


def test_station_markers_with_negative_speed_are_retrograde():
    chart = _parse("astro_paradeigma_5.pdf")
    by = {p.name: p for p in chart.points}
    # Ουρανός «(» και Χείρωνας «)» με αρνητική ταχύτητα: ήδη σε ανάδρομη κίνηση
    assert by["Ουρανός"].retrograde and by["Χείρωνας"].retrograde
    assert not by["Ήλιος"].retrograde
    assert {"Κρόνος", "Ποσειδώνας", "Πλούτωνας"} <= {p.name for p in chart.points if p.retrograde}
    assert (by["Ωροσκόπος"].sign, by["Ωροσκόπος"].degree) == ("Παρθένος", 9)


def test_direct_node_and_intercepted_signs():
    chart = _parse("astro_paradeigma_6.pdf")
    by = {p.name: p for p in chart.points}
    # Αληθής Δεσμός με «D» και θετική ταχύτητα: ΔΕΝ είναι σε ανάδρομη κίνηση
    assert not by["Βόρειος Δεσμός"].retrograde and not by["Νότιος Δεσμός"].retrograde
    signs = [c.sign for c in chart.cusps]
    # Δύο ακμές στο ίδιο ζώδιο (Καρκίνος, Αιγόκερως) και εγκλωβισμένα ζώδια
    assert signs[1] == signs[2] == "Καρκίνος" and signs[7] == signs[8] == "Αιγόκερως"
    assert "Κριός" not in signs and "Ζυγός" not in signs
