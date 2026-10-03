"""
test_reviewer_mutations.py
===========================
Regression tests για τα κενά που εντόπισε εξωτερική αξιολόγηση με
σκόπιμες αλλοιώσεις μιας σωστής ανάλυσης (validator v4). Κάθε test
αναπαράγει ακριβώς μία αλλοίωση που πριν περνούσε ως «πράσινη».
"""

from __future__ import annotations
from pathlib import Path

import pytest

import validator as V
from astrology import RULERS
from parser import parse_astrodienst_pdf
from test_english import build_analysis

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"
ARTICLE = {"Σελήνη": "η", "Αφροδίτη": "η"}


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


@pytest.fixture(scope="module")
def good(chart):
    text = build_analysis(chart, "el")
    assert V.validate_analysis(chart, text).ok
    return text


def _wrong_planet(chart, house):
    allowed = set(RULERS[chart.cusps[house - 1].sign])
    return next(p for p in ("Άρης", "Δίας", "Κρόνος", "Ερμής") if p not in allowed)


def _swap_ruler_in_house(chart, text, house, wrong):
    """Αλλάζει τον κυβερνήτη ΚΑΙ στο κυρίως κείμενο ΚΑΙ στο πλαίσιο, ώστε
    να μένουν συνεπή μεταξύ τους (αυτό περνούσε τον έλεγχο v3)."""
    seg = V._house_segments(text)[house]
    modern = RULERS[chart.cusps[house - 1].sign][0]
    art = ARTICLE.get(modern, "ο")
    new = seg.replace(f"Κύριος κυβερνήτης είναι {art} {modern}.", f"Κύριος κυβερνήτης είναι ο {wrong}.")
    new = new.replace(f"Κυβερνήτης: {modern}", f"Κυβερνήτης: {wrong}")
    assert new != seg
    return text.replace(seg, new, 1)


# --- Υψηλή: λάθος κυβερνήτης, συνεπής σε κείμενο και πλαίσιο --------------
def test_consistent_but_wrong_ruler_is_caught(chart, good):
    wrong = _wrong_planet(chart, 1)
    result = V.validate_analysis(chart, _swap_ruler_in_house(chart, good, 1, wrong))
    assert not result.ok
    assert not result.inconsistent_ruler_box  # ο έλεγχος v3 δεν το έβλεπε
    assert {(h, w, where) for h, w, _, where in result.wrong_ruler_claims} >= {
        (1, wrong, "κείμενο (κύριος)"),
        (1, wrong, "πλαίσιο"),
    } | {(1, f"(λείπει) {r}", "πλαίσιο") for r in RULERS[chart.cusps[0].sign] if r}


def test_box_comment_naming_other_planet_is_not_a_ruler_claim(chart, good):
    seg = V._house_segments(good)[1]
    line = next(l for l in seg.splitlines() if l.startswith("Κυβερνήτης:"))
    other = _wrong_planet(chart, 1)
    text = good.replace(line, f"{line}, σε τετράγωνο με τον {other}", 1)
    assert not V.validate_analysis(chart, text).wrong_ruler_claims


# --- Υψηλή: επινοημένη όψη --------------------------------------------------
def _fabricated_pair(chart):
    known = {frozenset((a.first, a.second)) for a in chart.aspects}
    pair = ("Ήλιος", "Σελήνη")
    assert frozenset(pair) not in known, "το fixture πρέπει να ΜΗΝ έχει όψη Ήλιου–Σελήνης"
    return pair


def test_fabricated_aspect_with_orb_fails(chart, good):
    _fabricated_pair(chart)
    seg = V._house_segments(good)[1]
    bad = good.replace(seg, seg + "Ήλιος–Σελήνη Τετράγωνο (orb 2°10′, Κανονική).\n", 1)
    result = V.validate_analysis(chart, bad)
    assert not result.ok
    assert [(a, b, t) for a, b, t, _ in result.undeclared_aspects] == [("Ήλιος", "Σελήνη", "Τετράγωνο")]


def test_fabricated_aspect_in_english_is_caught(chart):
    _fabricated_pair(chart)
    text = build_analysis(chart, "en")
    seg = V._house_segments(text)[1]
    bad = text.replace(seg, seg + "Sun–Moon Square (orb 2°10′, Standard).\n", 1)
    assert V.validate_analysis(chart, bad).undeclared_aspects


def test_known_aspects_are_never_flagged_as_fabricated(chart, good):
    assert not V.validate_analysis(chart, good).undeclared_aspects


# --- Μεσαία: ελλιπή πλαίσια σύνοψης -----------------------------------------
def test_removed_ruler_box_lines_fail(chart, good):
    bad = "\n".join(l for l in good.splitlines() if not l.startswith("Κυβερνήτης:"))
    result = V.validate_analysis(chart, bad)
    assert not result.ok
    assert result.missing_ruler_box == list(range(1, 13))


def test_empty_ruler_box_line_fails(chart, good):
    seg = V._house_segments(good)[3]
    line = next(l for l in seg.splitlines() if l.startswith("Κυβερνήτης:"))
    result = V.validate_analysis(chart, good.replace(line, "Κυβερνήτης: —", 1))
    assert result.missing_ruler_box == [3]


# ---------------------------------------------------------------------------
# Δεύτερος γύρος αξιολόγησης (validator v5)
# ---------------------------------------------------------------------------
def _add_to_house(text, house, sentence):
    seg = V._house_segments(text)[house]
    return text.replace(seg, seg + sentence + "\n", 1)


@pytest.mark.parametrize(
    "sentence",
    [
        # η ακριβής δοκιμή του reviewer
        "Ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη (orb 1°00′, Στενή/ισχυρή).",
        # χωρίς orb: πλέον σφάλμα, όχι προειδοποίηση
        "Ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη.",
        "Ο Ήλιος βρίσκεται σε τετράγωνο με τη Σελήνη.",
        "Ο Ήλιος σε τετράγωνο με τη Σελήνη δίνει ένταση.",
        "Ήλιος τετράγωνο Σελήνη (orb 1°00′).",
        "Το τετράγωνο Ήλιου–Σελήνης φέρνει ένταση.",
        "Το τετράγωνο του Ήλιου με τη Σελήνη φέρνει ένταση.",
        "Ήλιος–Σελήνη Τετράγωνο (orb 1°00′, Στενή/ισχυρή).",
        "Η Σελήνη σχηματίζει τετράγωνο με τον Ήλιο.",
    ],
)
def test_natural_greek_fabricated_aspect_fails(chart, good, sentence):
    _fabricated_pair(chart)
    result = V.validate_analysis(chart, _add_to_house(good, 1, sentence))
    assert not result.ok
    assert [(frozenset((a, b)), t) for a, b, t, _ in result.undeclared_aspects] == [
        (frozenset(("Ήλιος", "Σελήνη")), "Τετράγωνο")
    ]


@pytest.mark.parametrize(
    "sentence",
    [
        "The Sun forms a square with the Moon (orb 1°00′, Tight/strong).",
        "The Sun is in a square with the Moon.",
        "Sun square Moon (orb 1°00′).",
        "The square between the Sun and the Moon adds tension.",
        "The Sun–Moon square adds tension.",
    ],
)
def test_natural_english_fabricated_aspect_fails(chart, sentence):
    _fabricated_pair(chart)
    text = build_analysis(chart, "en")
    result = V.validate_analysis(chart, _add_to_house(text, 1, sentence))
    assert not result.ok
    assert result.undeclared_aspects


@pytest.mark.parametrize(
    "sentence",
    [
        # αρνήσεις
        "Ο Ήλιος δεν σχηματίζει τετράγωνο με τη Σελήνη.",
        "The Sun does not form a square with the Moon.",
        # αναφορά χωρίς δήλωση όψης
        "Ο Ήλιος και η Σελήνη συνεργάζονται εδώ.",
        "Ο Ήλιος, όπως και η Σελήνη, τονίζει το θέμα.",
        # αμφίσημο υποκείμενο: αγνοείται σκόπιμα
        "Ο Ήλιος φωτίζει, και τετράγωνο με τη Σελήνη δεν υπάρχει.",
    ],
)
def test_non_claims_are_not_flagged(chart, good, sentence):
    assert not V.validate_analysis(chart, _add_to_house(good, 1, sentence)).undeclared_aspects


def test_known_aspect_in_natural_sentence_is_not_flagged(chart, good):
    a = next(x for x in chart.aspects if x.aspect == "Τετράγωνο")
    art = ARTICLE.get(a.second, "τον")
    art = "τη" if art == "η" else "τον"
    sentence = f"Ο {a.first} σχηματίζει τετράγωνο με {art} {a.second} (orb {a.orb_text}, {a.weight})."
    assert not V.validate_analysis(chart, _add_to_house(good, 1, sentence)).undeclared_aspects


# --- ρόλος κυβερνήτη ---------------------------------------------------------
def _house_with_traditional(chart):
    return next(n for n in range(1, 13) if RULERS[chart.cusps[n - 1].sign][1])


def test_swapped_modern_and_traditional_ruler_fails(chart, good):
    """Η ακριβής δοκιμή του reviewer: π.χ. Κρόνος ως κύριος και Ουρανός ως
    παραδοσιακός σε Υδροχόο. Και τα δύο ονόματα είναι «επιτρεπτά»."""
    n = _house_with_traditional(chart)
    modern, traditional = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    am, at = ARTICLE.get(modern, "ο"), ARTICLE.get(traditional, "ο")
    swapped = seg.replace(f"Κύριος κυβερνήτης είναι {am} {modern}.", "@@M@@").replace(
        f"Παραδοσιακός κυβερνήτης είναι {at} {traditional}.", "@@T@@"
    )
    assert swapped.count("@@") == 4
    swapped = swapped.replace("@@M@@", f"Κύριος κυβερνήτης είναι {at} {traditional}.").replace(
        "@@T@@", f"Παραδοσιακός κυβερνήτης είναι {am} {modern}."
    )
    result = V.validate_analysis(chart, good.replace(seg, swapped, 1))
    assert not result.ok
    assert {(h, w, where) for h, w, _, where in result.wrong_ruler_claims} == {
        (n, traditional, "κείμενο (κύριος)"),
        (n, modern, "κείμενο (παραδοσιακός)"),
    }


def test_traditional_equal_to_modern_is_accepted(chart, good):
    """Ζώδιο χωρίς ξεχωριστό παραδοσιακό (π.χ. Κριός): «Παραδοσιακός
    κυβερνήτης είναι ο Άρης» είναι σωστό, όχι λάθος."""
    n = next(i for i in range(1, 13) if not RULERS[chart.cusps[i - 1].sign][1])
    modern = RULERS[chart.cusps[n - 1].sign][0]
    art = ARTICLE.get(modern, "ο")
    seg = V._house_segments(good)[n]
    line = f"Κύριος κυβερνήτης είναι {art} {modern}."
    text = good.replace(seg, seg.replace(line, f"{line}\nΠαραδοσιακός κυβερνήτης είναι {art} {modern}.", 1), 1)
    assert not V.validate_analysis(chart, text).wrong_ruler_claims


# ---------------------------------------------------------------------------
# Τρίτος γύρος (validator v6): η ΙΔΙΑ επινοημένη όψη (Ήλιος–Σελήνη τετράγωνο)
# σε πίνακα, πρόταση και διαφορετική σύνταξη -- όλες πρέπει να απορρίπτονται.
# ---------------------------------------------------------------------------
SAME_CLAIM_EL = [
    # γραμμές πίνακα (όπως τις γράφει το docx_text και το Παράρτημα)
    "Ήλιος–Σελήνη | Τετράγωνο | orb 1°00′ | Στενή/ισχυρή",
    "| Ήλιος–Σελήνη | Τετράγωνο | 1°00′ |",
    "Ήλιος | Σελήνη | Τετράγωνο | 1°00′",
    "Ήλιος | Τετράγωνο | Σελήνη",
    "Ήλιος / Σελήνη | τετράγωνο",
    # προτάσεις
    "Ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη.",
    "Δεν είναι εύκολο, επειδή ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη.",
    "Δεν υπάρχει αμφιβολία ότι ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη.",
    "Η ζωή δεν είναι απλή· ο Ήλιος σε τετράγωνο με τη Σελήνη το δείχνει.",
    "Το τετράγωνο του Ήλιου με τη Σελήνη φέρνει ένταση.",
    "Ήλιος–Σελήνη Τετράγωνο (orb 1°00′).",
]
SAME_CLAIM_EN = [
    "Sun–Moon | Square | orb 1°00′ | Tight/strong",
    "Sun | Moon | Square",
    "It is not easy, because the Sun forms a square with the Moon.",
    "There is no doubt that the Sun forms a square with the Moon.",
    "The Sun forms a square with the Moon.",
]


@pytest.mark.parametrize("line", SAME_CLAIM_EL)
def test_same_fabricated_claim_in_every_greek_form_fails(chart, good, line):
    _fabricated_pair(chart)
    result = V.validate_analysis(chart, _add_to_house(good, 1, line))
    assert not result.ok, line
    assert [(frozenset((a, b)), t) for a, b, t, _ in result.undeclared_aspects] == [
        (frozenset(("Ήλιος", "Σελήνη")), "Τετράγωνο")
    ]


@pytest.mark.parametrize("line", SAME_CLAIM_EN)
def test_same_fabricated_claim_in_every_english_form_fails(chart, line):
    _fabricated_pair(chart)
    result = V.validate_analysis(chart, _add_to_house(build_analysis(chart, "en"), 1, line))
    assert not result.ok, line
    assert result.undeclared_aspects


def test_fabricated_row_inside_appendix_fails(chart, good):
    _fabricated_pair(chart)
    bad = good + "\nΉλιος–Σελήνη | Τετράγωνο | orb 1°00′ | Στενή/ισχυρή"
    assert V.validate_analysis(chart, bad).undeclared_aspects


# Σωστές προτάσεις/γραμμές που ΠΡΕΠΕΙ να γίνονται δεκτές
CORRECT_NEGATIVES = [
    "Ο Ήλιος δεν σχηματίζει τετράγωνο με τη Σελήνη.",
    "Δεν υπάρχει τετράγωνο Ήλιου–Σελήνης στον χάρτη.",
    "Ο χάρτης δεν έχει τετράγωνο του Ήλιου με τη Σελήνη.",
    "Ούτε ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη.",
    "The Sun does not form a square with the Moon.",
    "There is no square between the Sun and the Moon.",
    # πίνακες που δεν είναι δηλώσεις όψης
    "Πλανήτης | Ζώδιο | Οίκος",
    "Ήλιος | Λέων | 5ος Οίκος",
    "Ήλιος | Σελήνη | Άρης | Τετράγωνο",  # τρία σημεία: αμφίσημο, αγνοείται
    "Βασική δύναμη | ο Ήλιος φωτίζει και η Σελήνη στηρίζει",
]


@pytest.mark.parametrize("line", CORRECT_NEGATIVES)
def test_correct_statements_are_accepted(chart, good, line):
    result = V.validate_analysis(chart, _add_to_house(good, 1, line))
    assert not result.undeclared_aspects, line
