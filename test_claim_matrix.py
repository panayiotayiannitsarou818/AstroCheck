"""
test_claim_matrix.py
=====================
Validator v7: κάθε δήλωση όψης συγκρίνεται με τον χάρτη ως
    ζεύγος -> τύπος -> orb -> βαρύτητα,
για γνωστά και άγνωστα ζεύγη, σε πρόζα και πίνακες, ελληνικά και αγγλικά.

Συστηματικός πίνακας: γλώσσα × μορφή × είδος λάθους. Σε ΚΑΘΕ περίπτωση η
λανθασμένη δήλωση ΠΡΟΣΤΙΘΕΤΑΙ σε ανάλυση που ήδη περνά, άρα οι σωστές
αναφορές του ίδιου ζεύγους παραμένουν αλλού στο έγγραφο. Αυτό ήταν ακριβώς
το κενό: η παρουσία μιας σωστής αναφοράς κάλυπτε μια πρόσθετη λανθασμένη.
"""

from __future__ import annotations
from pathlib import Path

import pytest

import lexicon_en as EN
import validator as V
from astrology import RULERS
from parser import integrity_problems, parse_astrodienst_pdf
from test_english import build_analysis

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"
FEMININE = {"Σελήνη", "Αφροδίτη"}
ACC = {
    "Ήλιος": "Ήλιο", "Σελήνη": "Σελήνη", "Ερμής": "Ερμή", "Αφροδίτη": "Αφροδίτη",
    "Άρης": "Άρη", "Δίας": "Δία", "Κρόνος": "Κρόνο", "Ουρανός": "Ουρανό",
    "Ποσειδώνας": "Ποσειδώνα", "Πλούτωνας": "Πλούτωνα", "Χείρωνας": "Χείρωνα",
}
ACC_TYPE = {"Σύνοδος": "σύνοδο", "Αντίθεση": "αντίθεση"}
PLANETS = set(ACC)
OTHER_WEIGHT = {
    "Στενή/ισχυρή": "Κανονική",
    "Κανονική": "Στενή/ισχυρή",
    "Πλατιά αλλά έγκυρη": "Στενή/ισχυρή",
    "Πολύ πλατιά/δευτερεύουσα": "Στενή/ισχυρή",
}


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


@pytest.fixture(scope="module")
def known(chart):
    """Μια γνωστή όψη ανάμεσα σε δύο πλανήτες, όχι αντίθεση."""
    return next(
        a for a in chart.aspects
        if a.first in PLANETS and a.second in PLANETS and a.aspect != "Αντίθεση"
    )


def _unknown_pair(chart):
    pairs = {frozenset((a.first, a.second)) for a in chart.aspects}
    names = sorted(PLANETS)
    return next((x, y) for x in names for y in names if x < y and frozenset((x, y)) not in pairs)


def _line(lang, fmt, first, second, aspect, orb, weight):
    if lang == "en":
        f, s, t, w = EN.en(first), EN.en(second), EN.en(aspect), EN.en(weight)
        return {
            "dash": f"{f}–{s} {t} (orb {orb}, {w}).",
            "natural": f"The {f} forms a {t.lower()} with the {s} (orb {orb}, {w}).",
            "table": f"{f}–{s} | {t} | orb {orb} | {w}",
            "table_cells": f"{f} | {s} | {t} | {orb}",
        }[fmt]
    art1 = "Η" if first in FEMININE else "Ο"
    art2 = "τη" if second in FEMININE else "τον"
    t_acc = ACC_TYPE.get(aspect, aspect.lower())
    return {
        "dash": f"{first}–{second} {aspect} (orb {orb}, {weight}).",
        "natural": f"{art1} {first} σχηματίζει {t_acc} με {art2} {ACC[second]} (orb {orb}, {weight}).",
        "table": f"{first}–{second} | {aspect} | orb {orb} | {weight}",
        "table_cells": f"{first} | {second} | {aspect} | {orb}",
    }[fmt]


def _add(text, sentence, house=1):
    seg = V._house_segments(text)[house]
    return text.replace(seg, seg + sentence + "\n", 1)


LANGS = ["el", "en"]
FORMATS = ["dash", "natural", "table", "table_cells"]
ERRORS = ["wrong_type", "wrong_orb", "wrong_weight", "undeclared"]


@pytest.mark.parametrize("error", ERRORS)
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("lang", LANGS)
def test_every_wrong_claim_is_caught(chart, known, lang, fmt, error):
    a = known
    first, second, aspect, orb, weight = a.first, a.second, a.aspect, a.orb_text, a.weight
    if error == "wrong_type":
        aspect = "Αντίθεση"
    elif error == "wrong_orb":
        orb = "0°01′"
    elif error == "wrong_weight":
        if fmt == "table_cells":
            pytest.skip("η μορφή χωριστών κελιών δεν έχει κελί βαρύτητας")
        weight = OTHER_WEIGHT[a.weight]
    else:
        first, second = _unknown_pair(chart)
    good = build_analysis(chart, lang)
    assert V.validate_analysis(chart, good).ok
    result = V.validate_analysis(chart, _add(good, _line(lang, fmt, first, second, aspect, orb, weight)))
    assert not result.ok, (lang, fmt, error)
    if error == "undeclared":
        assert result.undeclared_aspects
    else:
        assert result.aspect_claim_mismatches


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("lang", LANGS)
def test_correct_claim_in_every_format(chart, known, lang, fmt):
    """v9: δομημένες μορφές (γραμμή «Α–Β Τύπος (orb, Κατηγορία)», πίνακας)
    γίνονται δεκτές· ΣΩΣΤΗ όψη με orb μέσα σε πρόζα απορρίπτεται ΜΟΝΟ για
    τη θέση του αριθμού (όχι ως λάθος όψη)."""
    a = known
    line = _line(lang, fmt, a.first, a.second, a.aspect, a.orb_text, a.weight)
    result = V.validate_analysis(chart, _add(build_analysis(chart, lang), line))
    assert not result.aspect_claim_mismatches and not result.undeclared_aspects
    if fmt == "natural":
        assert not result.ok and result.stray_technical_values
    else:
        assert result.ok, (lang, fmt, result.details_lines())


# --- Οι ακριβείς δοκιμές του reviewer (γύρος 4) ------------------------------
def test_wrong_orb_on_known_pair_reviewer_case(chart, known):
    bad = f"{known.first}–{known.second} {known.aspect}, orb 0°01′."
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), bad)).aspect_claim_mismatches


def test_wrong_type_with_correct_orb_natural_sentence(chart, known):
    for lang in LANGS:
        line = _line(lang, "natural", known.first, known.second, "Αντίθεση", known.orb_text, known.weight)
        result = V.validate_analysis(chart, _add(build_analysis(chart, lang), line))
        assert result.aspect_claim_mismatches, lang


def test_table_aspect_cell_with_orb_in_parentheses(chart):
    first, second = _unknown_pair(chart)
    line = f"{first}–{second} | Τετράγωνο (1°00′)"
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), line)).undeclared_aspects


def test_position_degree_is_not_read_as_orb(chart, known):
    """«στις 12°30′» μετά από σωστή δήλωση δεν είναι orb."""
    art1 = "Η" if known.first in FEMININE else "Ο"
    art2 = "τη" if known.second in FEMININE else "τον"
    t = ACC_TYPE.get(known.aspect, known.aspect.lower())
    line = f"{art1} {known.first} σχηματίζει {t} με {art2} {ACC[known.second]}, με τον Ήλιο στις 21°55′ του Υδροχόου."
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), line)).ok


# --- Πληρότητα ρόλων κυβερνήτη ---------------------------------------------
def test_box_missing_modern_ruler_fails(chart):
    """Η δοκιμή του reviewer: αφαιρείται ο κύριος κυβερνήτης, μένει μόνο ο
    παραδοσιακός στο πλαίσιο."""
    good = build_analysis(chart, "el")
    n = next(i for i in range(1, 13) if RULERS[chart.cusps[i - 1].sign][1])
    modern, traditional = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    art = "η" if modern in FEMININE else "ο"
    bad_seg = seg.replace(f"Κύριος κυβερνήτης είναι {art} {modern}.\n", "").replace(
        f"Κυβερνήτης: {modern}, {traditional}", f"Κυβερνήτης: {traditional}"
    )
    assert bad_seg != seg
    result = V.validate_analysis(chart, good.replace(seg, bad_seg, 1))
    assert not result.ok
    assert (n, f"(λείπει) {modern}") in {(h, w) for h, w, _, _ in result.wrong_ruler_claims}


# --- Πληρότητα ανάγνωσης του πίνακα όψεων του PDF --------------------------
def test_integrity_detects_dropped_grid_aspect(chart):
    grid = [a for a in chart.aspects if a.source == "Πίνακας Astrodienst"]
    printed = {p.name: p.house for p in chart.points}
    one_less = [a for a in chart.aspects if a is not grid[0]]
    problems = integrity_problems(chart.points, chart.cusps, one_less, printed, grid_glyphs=len(grid))
    assert any("δεν διαβάστηκε πλήρως" in p for p in problems)


def test_integrity_complete_grid_passes(chart):
    grid = [a for a in chart.aspects if a.source == "Πίνακας Astrodienst"]
    printed = {p.name: p.house for p in chart.points}
    assert integrity_problems(chart.points, chart.cusps, chart.aspects, printed, grid_glyphs=len(grid)) == []


# ---------------------------------------------------------------------------
# Πέμπτος γύρος (validator v8): οι έξι δοκιμές του reviewer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "Ο Ήλιος σχηματίζει ισχυρό τετράγωνο με τη Σελήνη (orb 1°00′).",
        "Ο Ήλιος σχηματίζει ένα πολύ στενό τετράγωνο με τη Σελήνη.",
        "Ο Ήλιος βρίσκεται σε έντονο τετράγωνο με τη Σελήνη.",
    ],
)
def test_adjective_before_aspect_greek(chart, line):
    first, second = _unknown_pair(chart)
    line = line.replace("Ήλιος", first).replace("Σελήνη", ACC[second])
    line = line.replace("Ο " + first, ("Η " if first in FEMININE else "Ο ") + first)
    line = line.replace("με τη ", "με τη " if second in FEMININE else "με τον ")
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), line)).undeclared_aspects


@pytest.mark.parametrize(
    "tmpl",
    [
        "The {f} forms a strong square with the {s} (orb 1°00′).",
        "The {f} is in a very tight square with the {s}.",
        "The {f} makes a challenging square with the {s}.",
    ],
)
def test_adjective_before_aspect_english(chart, tmpl):
    first, second = _unknown_pair(chart)
    line = tmpl.format(f=EN.en(first), s=EN.en(second))
    assert V.validate_analysis(chart, _add(build_analysis(chart, "en"), line)).undeclared_aspects


def test_adjective_with_correct_known_aspect_is_accepted(chart, known):
    art1 = "Η" if known.first in FEMININE else "Ο"
    art2 = "τη" if known.second in FEMININE else "τον"
    t = ACC_TYPE.get(known.aspect, known.aspect.lower())
    line = f"{art1} {known.first} σχηματίζει ισχυρό {t} με {art2} {ACC[known.second]}."
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), line)).ok


def test_table_row_with_second_wrong_orb_fails(chart, known):
    a = known
    line = f"{a.first}–{a.second} | {a.aspect} | {a.orb_text} | 0°01′ | {a.weight}"
    result = V.validate_analysis(chart, _add(build_analysis(chart, "el"), line))
    assert not result.ok and result.aspect_claim_mismatches


def test_table_row_with_two_conflicting_weights_fails(chart, known):
    a = known
    line = f"{a.first}–{a.second} | {a.aspect} | {a.orb_text} | {a.weight} | {OTHER_WEIGHT[a.weight]}"
    result = V.validate_analysis(chart, _add(build_analysis(chart, "el"), line))
    assert not result.ok and result.aspect_claim_mismatches


def test_prose_with_two_conflicting_orbs_fails(chart, known):
    a = known
    line = f"{a.first}–{a.second} {a.aspect} (orb {a.orb_text}), δηλαδή orb 0°01′."
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), line)).aspect_claim_mismatches


@pytest.mark.parametrize("orb", ["0.01°", "0,01°", "5.5°"])
def test_decimal_wrong_orb_fails(chart, known, orb):
    a = known
    if abs(float(orb[:-1].replace(",", ".")) - a.orb) * 60 <= 1:
        pytest.skip("τυχαία σωστό")
    line = f"{a.first}–{a.second} {a.aspect}, orb {orb}."
    assert V.validate_analysis(chart, _add(build_analysis(chart, "el"), line)).aspect_claim_mismatches


def test_decimal_correct_orb_is_not_a_mismatch_but_is_unstructured(chart, known):
    a = known
    line = f"{a.first}–{a.second} {a.aspect}, orb {a.orb:.2f}°."
    result = V.validate_analysis(chart, _add(build_analysis(chart, "el"), line))
    assert not result.aspect_claim_mismatches
    assert result.stray_technical_values  # v9: δεκαδικό orb δεν είναι δομημένη μορφή


def test_ruler_declarations_removed_from_body_fail(chart):
    """Η δοκιμή του reviewer: αφαιρούνται ΟΛΕΣ οι δηλώσεις κυβερνητών από
    το κυρίως κείμενο, τα πλαίσια μένουν σωστά."""
    good = build_analysis(chart, "el")
    bad = "\n".join(
        l for l in good.splitlines()
        if not l.startswith(("Κύριος κυβερνήτης", "Παραδοσιακός κυβερνήτης"))
    )
    result = V.validate_analysis(chart, bad)
    assert not result.ok
    missing = {h for h, w, _, where in result.wrong_ruler_claims if where == "κυρίως κείμενο"}
    assert missing == set(range(1, 13))


@pytest.mark.parametrize(
    "phrase",
    [
        "Ο Οίκος κυβερνάται από τον {acc}.",
        "Κυβερνήτης του Οίκου είναι ο {nom}, που δίνει τον τόνο.",
        "Ο {nom}, κυβερνήτης αυτού του Οίκου, βρίσκεται αλλού.",
    ],
)
def test_free_ruler_wording_is_accepted(chart, phrase):
    """Οι οδηγίες δεν ορίζουν ακριβή διατύπωση: κάθε φυσική δήλωση αρκεί."""
    good = build_analysis(chart, "el")
    n = next(
        i for i in range(1, 13)
        if not RULERS[chart.cusps[i - 1].sign][1] and RULERS[chart.cusps[i - 1].sign][0] not in FEMININE
    )
    modern = RULERS[chart.cusps[n - 1].sign][0]
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.", phrase.format(nom=modern, acc=ACC[modern]))
    assert new != seg
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    assert not [x for x in result.wrong_ruler_claims if x[0] == n], result.wrong_ruler_claims


def test_box_with_traditional_first_fails(chart):
    good = build_analysis(chart, "el")
    n = next(i for i in range(1, 13) if RULERS[chart.cusps[i - 1].sign][1])
    modern, traditional = RULERS[chart.cusps[n - 1].sign]
    bad = good.replace(f"Κυβερνήτης: {modern}, {traditional}", f"Κυβερνήτης: {traditional}, {modern}", 1)
    assert bad != good
    result = V.validate_analysis(chart, bad)
    assert any(w.startswith("(σειρά)") for _, w, _, _ in result.wrong_ruler_claims)


def test_integrity_detects_two_glyphs_in_same_cell(chart):
    """Καταμέτρηση ίση και μαθηματικά σωστά, αλλά ένα κελί διπλό και ένα
    άλλο κενό: πρέπει να απορρίπτεται."""
    grid = [a for a in chart.aspects if a.source == "Πίνακας Astrodienst"]
    printed = {p.name: p.house for p in chart.points}
    swapped = [a for a in chart.aspects if a is not grid[1]] + [grid[0]]
    problems = integrity_problems(chart.points, chart.cusps, swapped, printed, grid_glyphs=len(grid))
    assert any("πιθανή λάθος αντιστοίχιση" in p for p in problems)
