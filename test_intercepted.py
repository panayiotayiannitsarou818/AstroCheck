"""Εγκλωβισμένα ζώδια: εντοπίζονται και σημειώνονται στην εντολή, χωρίς να
αλλάζει ο κανόνας του κυβερνήτη (μόνο από το ζώδιο της ακμής)."""

from pathlib import Path

from parser import parse_astrodienst_pdf
from prompts import house_section, intercepted_signs

FIX = Path(__file__).parent / "fixtures"


def _chart(name):
    return parse_astrodienst_pdf((FIX / name).read_bytes(), name)


def test_intercepted_signs_are_found():
    c = _chart("astro_paradeigma_6.pdf")
    found = {n: intercepted_signs(c.cusps[n - 1], c.cusps[n % 12]) for n in range(1, 13)}
    assert found[5] == ["Ζυγός"] and found[11] == ["Κριός"]
    assert all(not v for n, v in found.items() if n not in (5, 11))


def test_note_in_prompt_keeps_cusp_ruler():
    section = house_section(_chart("astro_paradeigma_6.pdf"), 5)
    assert "Εγκλωβισμένο ζώδιο: Ζυγός" in section
    assert "κυβερνήτης του εγκλωβισμένου ζωδίου δεν γίνεται κυβερνήτης" in section


def test_no_note_when_nothing_is_intercepted():
    c = _chart("astro_paradeigma_2.pdf")
    assert all("Εγκλωβισμέν" not in house_section(c, n) for n in range(1, 13))
