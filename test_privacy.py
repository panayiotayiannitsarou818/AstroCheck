"""Απόρρητο εξ ορισμού: χωρίς καμία ενέργεια του χρήστη, ό,τι στέλνεται
έχει αρχικά αντί για όνομα και χωρίς γενέθλια στοιχεία -- ενώ τα
αστρολογικά δεδομένα μένουν ανέπαφα."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from case_state import CASE_STATE_KEYS
from parser import parse_astrodienst_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"


def _app(name):
    chart = parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)
    chart.name = name
    at = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60)
    at.session_state.chart = chart
    return at.run()


def _sent(at):
    return " ".join(c.value for c in at.code)


def test_initials_and_hidden_birth_by_default():
    at = _app("Elena Kakouli")
    sent = _sent(at)
    assert not at.exception
    assert "του/της E.K." in sent and "Elena" not in sent and "Kakouli" not in sent
    assert at.session_state.hide_birth is True
    original = at.session_state.chart
    assert original.name == "Elena Kakouli" and "1982" in original.date  # αρχικός χάρτης ανέπαφος


def test_filename_fallback_becomes_neutral():
    assert "του/της Πελάτης" in _sent(_app("astro_paradeigma_2"))


def test_birth_data_can_be_shown_on_request():
    at = _app("Panayiota")
    at.checkbox(key="hide_birth").uncheck()
    at.run()
    assert not at.exception and at.session_state.hide_birth is False


def test_privacy_choice_resets_with_new_case():
    assert "hide_birth" in CASE_STATE_KEYS
