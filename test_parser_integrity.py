"""Ο έλεγχος ακεραιότητας πρέπει να «πιάνει» λάθος ανάγνωση του PDF
(π.χ. μετά από αλλαγή διάταξης της Astrodienst) αντί να περνά αθόρυβα."""

import copy
from pathlib import Path

import pytest

from parser import integrity_problems, parse_astrodienst_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma.pdf"


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


def _check(chart, points=None, cusps=None, aspects=None, printed=None):
    points = points if points is not None else chart.points
    return integrity_problems(
        points,
        cusps if cusps is not None else chart.cusps,
        aspects if aspects is not None else chart.aspects,
        printed if printed is not None else {p.name: p.house for p in points},
    )


def test_real_pdf_is_consistent(chart):
    assert _check(chart) == []


def test_misread_planet_degree_is_caught(chart):
    points = copy.deepcopy(chart.points)
    sun = next(p for p in points if p.name == "Ήλιος")
    sun.absolute = (sun.absolute + 1) % 360  # λάθος ανάγνωση κατά 1°
    assert any("Ήλιος" in p and "orb" in p for p in _check(chart, points=points))


def test_house_mismatch_with_pdf_is_caught(chart):
    printed = {p.name: p.house for p in chart.points}
    printed["Σελήνη"] = (printed["Σελήνη"] % 12) + 1
    assert any("Σελήνη" in p and "Οίκο" in p for p in _check(chart, printed=printed))


def test_misread_cusp_is_caught(chart):
    cusps = copy.deepcopy(chart.cusps)
    cusps[1].absolute = (cusps[1].absolute + 0.5) % 360
    assert any("ακμές 2 και 8" in p for p in _check(chart, cusps=cusps))


def test_missing_planet_is_caught(chart):
    points = [p for p in chart.points if p.name != "Χείρωνας"]
    assert any("Χείρωνας" in p for p in _check(chart, points=points))


def test_missing_aspect_table_is_caught(chart):
    assert any("όψεις" in p for p in _check(chart, aspects=[]))
