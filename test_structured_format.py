"""
test_structured_format.py
==========================
Validator v9 / Odigies v6 κανόνας 5: ΔΟΜΗΜΕΝΗ ΜΟΡΦΗ τεχνικών δηλώσεων.

    Ήλιος–Σελήνη Τετράγωνο (orb 1°13′, Στενή/ισχυρή)      <- δική του γραμμή

Αριθμοί orb επιτρέπονται ΜΟΝΟ σε δομημένες γραμμές και στο Παράρτημα. Η
πρόζα ερμηνεύει χωρίς αριθμούς· όψεις που αναφέρει χωρίς αριθμούς ελέγχονται
ακόμη για ζεύγος/τύπο με γενική σύνταξη (όχι λίστα ρημάτων).
"""

from __future__ import annotations
from pathlib import Path

import pytest

import lexicon_en as EN
import validator as V
from astrology import RULERS
from parser import parse_astrodienst_pdf
from test_english import build_analysis

FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


@pytest.fixture(scope="module")
def good(chart):
    return build_analysis(chart, "el")


def _add(text, line, house=1):
    seg = V._house_segments(text)[house]
    return text.replace(seg, seg + line + "\n", 1)


def _assert_fabricated_sun_moon(chart):
    assert frozenset(("Ήλιος", "Σελήνη")) not in {frozenset((a.first, a.second)) for a in chart.aspects}


# --- Τα πέντε ευρήματα του έκτου γύρου ---------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "Ήλιος–Σελήνη: Τετράγωνο (orb 1°00′)",
        "Ήλιος–Σελήνη — Τετράγωνο (orb 1°00′)",
        "Ο Ήλιος παρουσιάζει τετράγωνο με τη Σελήνη.",
    ],
)
def test_round6_fabricated_forms_fail(chart, good, line):
    _assert_fabricated_sun_moon(chart)
    result = V.validate_analysis(chart, _add(good, line))
    assert not result.ok
    assert result.undeclared_aspects


def test_round6_orb_equals_sign_fails(chart, good):
    a = next(x for x in chart.aspects if x.first == "Σελήνη" and x.second == "Ερμής")
    result = V.validate_analysis(chart, _add(good, f"Σελήνη–Ερμής {a.aspect} (orb = 0°01′)"))
    assert not result.ok
    assert result.aspect_claim_mismatches or result.stray_technical_values


def _aquarius_like_house(chart):
    return next(n for n in range(1, 13) if RULERS[chart.cusps[n - 1].sign][1])


@pytest.mark.parametrize(
    "modern_sentence, trad_sentence",
    [
        ("Ο {t} είναι ο κύριος κυβερνήτης.", "Ο {m} είναι ο παραδοσιακός κυβερνήτης."),
        ("Κύριος κυβερνήτης είναι ο {t}.", "Παραδοσιακός κυβερνήτης είναι ο {m}."),
        ("Ο σύγχρονος κυβερνήτης του Οίκου είναι ο {t}.", "Παραδοσιακά τον κυβερνά ο {m}."),
    ],
)
def test_round6_role_inversion_in_any_word_order_fails(chart, good, modern_sentence, trad_sentence):
    n = _aquarius_like_house(chart)
    modern, trad = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.", modern_sentence.format(t=trad, m=modern))
    new = new.replace(f"Παραδοσιακός κυβερνήτης είναι ο {trad}.", trad_sentence.format(t=trad, m=modern))
    assert new != seg
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    roles = {(w, where) for h, w, _, where in result.wrong_ruler_claims if h == n}
    assert (trad, "κείμενο (κύριος)") in roles, roles


@pytest.mark.parametrize(
    "sentence",
    [
        "Ο {m} είναι ο κύριος κυβερνήτης, ενώ ο {t} είναι ο παραδοσιακός.",
        "Κύριος κυβερνήτης είναι ο {m} και παραδοσιακός ο {t}.",
        "Ο Οίκος έχει κυβερνήτη τον {m_acc} — παραδοσιακά τον {t_acc}.",
        "Ο {t}, ως παραδοσιακός κυβερνήτης, συμπληρώνει τον {m_acc}, που είναι ο κύριος κυβερνήτης.",
    ],
)
def test_correct_roles_in_varied_wording_are_accepted(chart, good, sentence):
    ACC = {"Ουρανός": "Ουρανό", "Κρόνος": "Κρόνο", "Πλούτωνας": "Πλούτωνα", "Άρης": "Άρη",
           "Ποσειδώνας": "Ποσειδώνα", "Δίας": "Δία"}
    n = _aquarius_like_house(chart)
    modern, trad = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.\n", "").replace(
        f"Παραδοσιακός κυβερνήτης είναι ο {trad}.",
        sentence.format(m=modern, t=trad, m_acc=ACC[modern], t_acc=ACC[trad]),
    )
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    assert not [x for x in result.wrong_ruler_claims if x[0] == n], result.wrong_ruler_claims


# --- Στίξη × σειρά λέξεων (πρόταση reviewer) -------------------------------
SEPARATORS = ["", ":", " —", " –", " -"]
ORDERS_EL = [
    "{a}–{b}{sep} Τετράγωνο",
    "Τετράγωνο {a_gen}–{b_gen}",
    "Το τετράγωνο του {a_gen} με τη {b}",
    "Ο {a} {verb} τετράγωνο με τη {b}",
    "Ο {a} {verb} ένα ιδιαίτερα έντονο τετράγωνο με τη {b}",
]
VERBS = ["σχηματίζει", "παρουσιάζει", "δέχεται", "μοιράζεται", "έχει"]


@pytest.mark.parametrize("sep", SEPARATORS)
def test_separator_variants_fail(chart, good, sep):
    _assert_fabricated_sun_moon(chart)
    line = ORDERS_EL[0].format(a="Ήλιος", b="Σελήνη", sep=sep) + "."
    assert V.validate_analysis(chart, _add(good, line)).undeclared_aspects, line


@pytest.mark.parametrize("order", ORDERS_EL[1:])
@pytest.mark.parametrize("verb", VERBS)
def test_word_order_and_verb_variants_fail(chart, good, order, verb):
    _assert_fabricated_sun_moon(chart)
    line = order.format(a="Ήλιος", b="Σελήνη", a_gen="Ήλιου", b_gen="Σελήνης", verb=verb) + "."
    assert V.validate_analysis(chart, _add(good, line)).undeclared_aspects, line


@pytest.mark.parametrize("verb", ["forms", "shows", "receives", "has", "shares"])
def test_english_verb_variants_fail(chart, verb):
    _assert_fabricated_sun_moon(chart)
    line = f"The Sun {verb} a tense square with the Moon."
    text = build_analysis(chart, "en")
    assert V.validate_analysis(chart, _add(text, line)).undeclared_aspects, line


def test_hypothetical_mention_is_reported_accurately(chart, good):
    _assert_fabricated_sun_moon(chart)
    result = V.validate_analysis(chart, _add(good, "Αν ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη, αυτό θα ήταν σημαντικό."))
    assert result.undeclared_aspects
    assert any("δεν υπάρχει στον χάρτη" in l for l in result.details_lines())
    assert not any("Επινοημένη" in l for l in result.details_lines())


# --- Κανόνας δομημένης μορφής ------------------------------------------------
def test_orb_in_summary_box_fails(chart, good):
    a = chart.aspects[0]
    seg = V._house_segments(good)[1]
    line = next(l for l in seg.splitlines() if l.startswith("Βασική πρόκληση:"))
    bad = good.replace(line, f"Βασική πρόκληση: η όψη {a.first}–{a.second} (orb {a.orb_text}).", 1)
    assert V.validate_analysis(chart, bad).stray_technical_values


@pytest.mark.parametrize(
    "line",
    [
        "Ο Ήλιος στις 12°30′ του Λέοντα.",
        "Ακμή 5ου Οίκου: 3°12′ Καρκίνου.",
        "Λέων 12°30′, στον 5ο Οίκο.",
        "Ο Ερμής βρίσκεται 0°27′ από την επόμενη ακμή.",
        "Η απόσταση είναι 0°27′ από την ακμή του 6ου.",
        "The Sun at 12°30′ Leo.",
        "Η χιαστί όψη 150° είναι λεπτή όψη.",
        "Σύμφωνα με τη Θεωρία των Μοιρών, οι 22° έχουν αιγοκερίσια χροιά.",
    ],
)
def test_positions_and_cusp_distances_are_allowed(chart, good, line):
    assert not V.validate_analysis(chart, _add(good, line)).stray_technical_values, line


@pytest.mark.parametrize("bullet", ["", "- ", "• "])
def test_structured_line_with_bullet_is_accepted(chart, good, bullet):
    a = chart.aspects[0]
    line = f"{bullet}{a.first}–{a.second} {a.aspect} (orb {a.orb_text}, {a.weight})"
    assert V.validate_analysis(chart, _add(good, line)).ok


def test_structured_line_with_colon_is_accepted(chart, good):
    a = chart.aspects[0]
    line = f"{a.first}–{a.second}: {a.aspect} (orb {a.orb_text}, {a.weight})"
    assert V.validate_analysis(chart, _add(good, line)).ok


def test_prose_interpretation_without_numbers_is_accepted(chart, good):
    a = next(x for x in chart.aspects if {x.first, x.second} == {"Αφροδίτη", "Κρόνος"})
    assert a.aspect == "Τετράγωνο"
    line = "Η Αφροδίτη σε τετράγωνο με τον Κρόνο μπορεί να δείχνει σοβαρότητα στις σχέσεις."
    assert V.validate_analysis(chart, _add(good, line)).ok


def test_all_fixtures_both_languages_still_pass():
    for pdf in sorted((Path(__file__).parent / "fixtures").glob("*.pdf")):
        c = parse_astrodienst_pdf(pdf.read_bytes(), pdf.name)
        for lang in ("el", "en"):
            r = V.validate_analysis(c, build_analysis(c, lang))
            assert r.ok, (pdf.name, lang, r.details_lines()[:3])


# --- Έλεγχος σε ρεαλιστική πρόζα: αναφορές χωρίς όψη δεν είναι δηλώσεις ----
REALISTIC_NON_CLAIMS = [
    "Ο Ήλιος στον Λέοντα και η Σελήνη στον Καρκίνο δίνουν ένα θερμό αλλά ευαίσθητο υπόβαθρο.",
    "Η Αφροδίτη, κυβερνήτης του 7ου Οίκου, βρίσκεται κοντά στον Άρη στον ίδιο Οίκο.",
    "Ο Κρόνος ως κυβερνήτης του 10ου συνδέεται θεματικά με τον Δία στον 9ο.",
    "Όπως ο Ερμής, έτσι και η Αφροδίτη τονίζει την ανάγκη για επικοινωνία.",
    "Ο Ήλιος φωτίζει τον 5ο Οίκο και η Σελήνη τον 4ο, δύο πεδία που αλληλοτροφοδοτούνται.",
    "Ο Δίας στον Τοξότη και ο Ουρανός στον Υδροχόο μοιράζονται μια ανάγκη ελευθερίας.",
    "Στο τρίγωνο Οίκων 2ος-6ος-10ος ο Κρόνος και ο Δίας έχουν κεντρικό ρόλο.",
    "Η αντίθεση ανάμεσα στον Ήλιο και τη Σελήνη δεν υπάρχει σε αυτόν τον χάρτη.",
    "Ο Βόρειος Δεσμός στον Ζυγό και ο Νότιος στον Κριό σχηματίζουν τον άξονα των σχέσεων.",
    "The Sun in Leo and the Moon in Cancer give a warm background.",
    "Venus, ruler of the 7th House, sits close to Mars.",
    "A square between the Sun and the Moon does not exist in this chart.",
]


@pytest.mark.parametrize("line", REALISTIC_NON_CLAIMS)
def test_realistic_non_claims_are_not_read_as_aspects(line):
    import validation_aspects as VA
    assert VA._aspect_claims(line) == [], line


@pytest.mark.parametrize(
    "line",
    [
        "Ο Ήλιος, που σχηματίζει τετράγωνο με τη Σελήνη, δίνει ένταση.",
        "Ο Ήλιος, ο οποίος βρίσκεται σε τετράγωνο με τη Σελήνη, δίνει ένταση.",
        "The Sun, which forms a square with the Moon, adds tension.",
    ],
)
def test_relative_clause_claims_are_read(chart, good, line):
    _assert_fabricated_sun_moon(chart)
    text = good if not line.startswith("The") else build_analysis(chart, "en")
    assert V.validate_analysis(chart, _add(text, line)).undeclared_aspects, line


# ---------------------------------------------------------------------------
# Έβδομος γύρος (validator v10)
# ---------------------------------------------------------------------------
def _moon_mercury(chart):
    return next(a for a in chart.aspects if {a.first, a.second} == {"Σελήνη", "Ερμής"})


# Η βασική εγγύηση: ό,τι γίνεται δεκτό ως δομημένο έχει διαβαστεί ΠΛΗΡΩΣ.
def test_every_accepted_structured_line_is_fully_read():
    import validation_aspects as VA
    for pdf in sorted((Path(__file__).parent / "fixtures").glob("*.pdf")):
        c = parse_astrodienst_pdf(pdf.read_bytes(), pdf.name)
        for lang in ("el", "en"):
            for line in build_analysis(c, lang).splitlines():
                if VA._TECH_VALUE.search(line) and VA._is_structured(line):
                    claims = VA._aspect_claims(line)
                    if not claims:  # πίνακας θέσεων: ο αριθμός είναι θέση με ζώδιο
                        continue
                    assert len(claims) == 1, line
                    assert claims[0][3], ("orb δεν διαβάστηκε", line)


@pytest.mark.parametrize("orb_cell", ["orb = 0°01′", "orb: 0°01′", "orb 0°01′", "0°01′", "orb=0.01°"])
def test_wrong_orb_in_any_cell_form_fails(chart, good, orb_cell):
    a = _moon_mercury(chart)
    line = f"{a.first}–{a.second} | {a.aspect} | {orb_cell} | {a.weight}"
    result = V.validate_analysis(chart, _add(good, line))
    assert not result.ok and result.aspect_claim_mismatches, orb_cell


@pytest.mark.parametrize("orb_cell", ["orb = {o}", "orb: {o}", "orb {o}", "{o}"])
def test_correct_orb_in_any_cell_form_is_accepted(chart, good, orb_cell):
    a = _moon_mercury(chart)
    line = f"{a.first}–{a.second} | {a.aspect} | {orb_cell.format(o=a.orb_text)} | {a.weight}"
    assert V.validate_analysis(chart, _add(good, line)).ok, line


@pytest.mark.parametrize(
    "row",
    [
        "Ήλιος–Σελήνη | Τετράγωνο | Αντίθεση",           # δύο τύποι (η δοκιμή του reviewer)
        "Ήλιος | Σελήνη | Άρης | Τετράγωνο",            # τρία σημεία
        "Ήλιος–Σελήνη | 1°00′ | Κανονική",              # λείπει ο τύπος
        "Σελήνη–Ερμής | Τρίγωνο | περίπου 7° | Κανονική",  # μη αναγνώσιμο τεχνικό κελί
    ],
)
def test_ambiguous_or_incomplete_aspect_rows_fail(chart, good, row):
    result = V.validate_analysis(chart, _add(good, row))
    assert not result.ok
    assert result.malformed_aspect_rows, row


@pytest.mark.parametrize(
    "row",
    [
        "Ήλιος | Λέων | 12°30′ | 5ος Οίκος",
        "Ωροσκόπος | Καρκίνος | 5°12′",
        "Ήλιος | 12°30′ Λέοντα",
        "1ος Οίκος | Τοξότης | 3°12′",
        "Πλανήτης | Ζώδιο | Μοίρες | Οίκος",
        "Ζεύγος | Όψη | Orb | Κατηγορία",
        "Sun | Leo | 12°30′ | 5th House",
    ],
)
def test_data_and_header_tables_are_accepted(chart, good, row):
    """Ο πίνακας βασικών δεδομένων (Odigies §12) δεν είναι γραμμή όψης."""
    result = V.validate_analysis(chart, _add(good, row))
    assert result.ok, (row, result.details_lines()[:2])


# --- Κυβερνήτες: η στίξη δεν αποσυνδέει όνομα από ρόλο ---------------------
@pytest.mark.parametrize(
    "modern_line, trad_line",
    [
        ("Κύριος κυβερνήτης: {t}.", "Παραδοσιακός κυβερνήτης: {m}."),           # η δοκιμή του reviewer
        ("Ο {t}, κύριος κυβερνήτης του Οίκου, δίνει τον τόνο.", "Ο {m}, παραδοσιακός κυβερνήτης, συμπληρώνει."),
        ("Κύριος κυβερνήτης, ο {t}, δίνει τον τόνο.", "Παραδοσιακός, ο {m}."),
    ],
)
def test_role_inversion_with_punctuation_fails(chart, good, modern_line, trad_line):
    n = _aquarius_like_house(chart)
    modern, trad = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.", modern_line.format(t=trad, m=modern))
    new = new.replace(f"Παραδοσιακός κυβερνήτης είναι ο {trad}.", trad_line.format(t=trad, m=modern))
    assert new != seg
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    roles = {(w, where) for h, w, _, where in result.wrong_ruler_claims if h == n}
    assert (trad, "κείμενο (κύριος)") in roles, roles
    assert not result.ok


@pytest.mark.parametrize(
    "modern_line, trad_line",
    [
        ("Κύριος κυβερνήτης: {m}.", "Παραδοσιακός κυβερνήτης: {t}."),
        ("Ο {m}, κύριος κυβερνήτης του Οίκου, δίνει τον τόνο.", "Ο {t}, παραδοσιακός κυβερνήτης, συμπληρώνει."),
        ("Κύριος κυβερνήτης, ο {m}, δίνει τον τόνο.", "Παραδοσιακός, ο {t}."),
    ],
)
def test_correct_roles_with_punctuation_are_accepted(chart, good, modern_line, trad_line):
    n = _aquarius_like_house(chart)
    modern, trad = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.", modern_line.format(t=trad, m=modern))
    new = new.replace(f"Παραδοσιακός κυβερνήτης είναι ο {trad}.", trad_line.format(t=trad, m=modern))
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    assert not [x for x in result.wrong_ruler_claims if x[0] == n], result.wrong_ruler_claims


# --- Πρόζα: παρενθετική φράση με κόμματα ------------------------------------
@pytest.mark.parametrize(
    "line, lang",
    [
        ("Ο Ήλιος, σε τετράγωνο με τη Σελήνη, δείχνει ένταση.", "el"),
        ("Ο Ήλιος, σε ένα έντονο τετράγωνο με τη Σελήνη, δείχνει ένταση.", "el"),
        ("The Sun, in square with the Moon, shows tension.", "en"),
    ],
)
def test_appositive_claim_fails(chart, line, lang):
    _assert_fabricated_sun_moon(chart)
    text = build_analysis(chart, lang)
    assert V.validate_analysis(chart, _add(text, line)).undeclared_aspects, line


def test_odigies_own_ruler_wording_is_accepted(chart, good):
    """Η διατύπωση του κανόνα 3 των οδηγιών: «Ουρανός — παραδοσιακά Κρόνος»."""
    n = _aquarius_like_house(chart)
    modern, trad = RULERS[chart.cusps[n - 1].sign]
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.\n", "").replace(
        f"Παραδοσιακός κυβερνήτης είναι ο {trad}.", f"{chart.cusps[n - 1].sign}: {modern} — παραδοσιακά {trad}."
    )
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    assert not [x for x in result.wrong_ruler_claims if x[0] == n], result.wrong_ruler_claims


# ---------------------------------------------------------------------------
# Όγδοος γύρος (validator v11)
# ---------------------------------------------------------------------------
import itertools

ACC_ART = {
    "Ήλιος": "τον Ήλιο", "Σελήνη": "τη Σελήνη", "Ερμής": "τον Ερμή", "Αφροδίτη": "την Αφροδίτη",
    "Άρης": "τον Άρη", "Δίας": "τον Δία", "Κρόνος": "τον Κρόνο", "Ουρανός": "τον Ουρανό",
    "Ποσειδώνας": "τον Ποσειδώνα", "Πλούτωνας": "τον Πλούτωνα", "Χείρωνας": "τον Χείρωνα",
}
TYPE_ACC = {"Σύνοδος": "σύνοδο", "Αντίθεση": "αντίθεση", "Τετράγωνο": "τετράγωνο",
            "Τρίγωνο": "τρίγωνο", "Εξάγωνο": "εξάγωνο"}

COMPOUND_TEMPLATES = [
    "{S} σχηματίζει {t1} με {o1} και {t2} με {o2}.",
    "{S} σχηματίζει {t1} με {o1}, και {t2} με {o2}.",
    "{S} σχηματίζει {t1} με {o1}, ενώ {t2} με {o2}.",
    "{S} βρίσκεται σε {t1} με {o1} και σε {t2} με {o2}.",
    "{S} έχει ένα στενό {t1} με {o1} και ένα πλατύ {t2} με {o2}.",
    "{S}, σε {t1} με {o1} και σε {t2} με {o2}, δίνει ευελιξία.",
]


def _subject_with_two_aspects(chart):
    for subj in ACC_ART:
        partners = [
            (a.second if a.first == subj else a.first, a.aspect)
            for a in chart.aspects
            if subj in (a.first, a.second) and a.aspect in TYPE_ACC
        ]
        partners = [p for p in partners if p[0] in ACC_ART]
        if len(partners) >= 2:
            return subj, partners[0], partners[1]
    raise AssertionError("δεν βρέθηκε κατάλληλο υποκείμενο")


def _unaspected_partner(chart, subj):
    linked = {a.first for a in chart.aspects if a.second == subj} | {a.second for a in chart.aspects if a.first == subj}
    return next(p for p in ACC_ART if p != subj and p not in linked)


def _compound(tmpl, subj, p1, p2):
    art = "Η" if subj in ("Σελήνη", "Αφροδίτη") else "Ο"
    return tmpl.format(S=f"{art} {subj}", t1=TYPE_ACC[p1[1]], o1=ACC_ART[p1[0]],
                       t2=TYPE_ACC[p2[1]], o2=ACC_ART[p2[0]])


@pytest.mark.parametrize("tmpl", COMPOUND_TEMPLATES)
def test_correct_compound_sentence_is_accepted(chart, good, tmpl):
    """Η λανθασμένη απόρριψη του reviewer: το δεύτερο τρίγωνο ανήκει στο
    ΥΠΟΚΕΙΜΕΝΟ (Σελήνη), όχι στον Ερμή."""
    subj, p1, p2 = _subject_with_two_aspects(chart)
    line = _compound(tmpl, subj, p1, p2)
    result = V.validate_analysis(chart, _add(good, line))
    assert result.ok, (line, result.details_lines()[:2])


@pytest.mark.parametrize("tmpl", COMPOUND_TEMPLATES)
def test_compound_sentence_with_wrong_second_partner_fails(chart, good, tmpl):
    subj, p1, p2 = _subject_with_two_aspects(chart)
    wrong = (_unaspected_partner(chart, subj), p2[1])
    line = _compound(tmpl, subj, p1, wrong)
    result = V.validate_analysis(chart, _add(good, line))
    assert {frozenset((a, b)) for a, b, _, _ in result.undeclared_aspects} == {frozenset((subj, wrong[0]))}, line


def test_reviewer_exact_compound_sentence(chart, good):
    line = "Η Σελήνη σχηματίζει τρίγωνο με τον Ερμή και τρίγωνο με Αφροδίτη."
    assert V.validate_analysis(chart, _add(good, line)).ok


# --- Ίδιο σημείο δύο φορές --------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "Ήλιος–Ήλιος Τετράγωνο (orb 1°00′, Στενή/ισχυρή)",
        "Ήλιος–Ήλιος | Τετράγωνο | orb 1°00′ | Στενή/ισχυρή",
        "Ήλιος | Ήλιος | Τετράγωνο | 1°00′",
    ],
)
def test_same_point_twice_fails(chart, good, line):
    result = V.validate_analysis(chart, _add(good, line))
    assert not result.ok and result.malformed_aspect_rows, line


# --- Ετικέτες κελιών: ίδια ανάγνωση με ή χωρίς ετικέτα ----------------------
@pytest.mark.parametrize("labels", list(itertools.product(["", "Ζεύγος: "], ["", "Όψη: "], ["", "Orb: "])))
def test_labelled_cells_wrong_and_correct(chart, good, labels):
    lp, la, lo = labels
    _assert_fabricated_sun_moon(chart)
    bad = f"{lp}Ήλιος–Σελήνη | {la}Τετράγωνο | {lo}1°00′ | Λέων"
    assert not V.validate_analysis(chart, _add(good, bad)).ok, bad
    a = _moon_mercury(chart)
    ok_row = f"{lp}{a.first}–{a.second} | {la}{a.aspect} | {lo}{a.orb_text} | {a.weight}"
    assert V.validate_analysis(chart, _add(good, ok_row)).ok, ok_row


# --- Ρόλοι κυβερνήτη μέσα σε παρένθεση ---------------------------------------
@pytest.mark.parametrize(
    "modern_tmpl, trad_tmpl",
    [
        ("Ο {x} (κύριος κυβερνήτης) δίνει τον τόνο.", "Ο {y} (παραδοσιακός κυβερνήτης) συμπληρώνει."),
        ("Ο {x} (κύριος κυβερνήτης του Οίκου) δίνει τον τόνο.", "Ο {y} (παραδοσιακά) συμπληρώνει."),
    ],
)
@pytest.mark.parametrize("swap", [False, True])
def test_roles_in_parentheses(chart, good, modern_tmpl, trad_tmpl, swap):
    n = _aquarius_like_house(chart)
    modern, trad = RULERS[chart.cusps[n - 1].sign]
    x, y = (trad, modern) if swap else (modern, trad)
    seg = V._house_segments(good)[n]
    new = seg.replace(f"Κύριος κυβερνήτης είναι ο {modern}.", modern_tmpl.format(x=x))
    new = new.replace(f"Παραδοσιακός κυβερνήτης είναι ο {trad}.", trad_tmpl.format(y=y))
    result = V.validate_analysis(chart, good.replace(seg, new, 1))
    body_errors = [r for r in result.wrong_ruler_claims if r[0] == n]
    if swap:
        assert (trad, "κείμενο (κύριος)") in {(w, where) for _, w, _, where in body_errors}
    else:
        assert not body_errors, body_errors


# ---------------------------------------------------------------------------
# Ένατος γύρος (validator v12)
# ---------------------------------------------------------------------------
def _known(chart, x, y):
    return next((a for a in chart.aspects if {a.first, a.second} == {x, y}), None)


# 1. Νέο υποκείμενο στην ίδια πρόταση (η λανθασμένη απόρριψη του reviewer)
def test_new_subject_in_same_sentence_correct_is_accepted(chart, good):
    assert _known(chart, "Σελήνη", "Ερμής") and _known(chart, "Αφροδίτη", "Άρης") and _known(chart, "Αφροδίτη", "Κρόνος")
    line = ("Η Σελήνη σχηματίζει τρίγωνο με τον Ερμή, η Αφροδίτη σχηματίζει "
            "τετράγωνο με τον Άρη και τετράγωνο με τον Κρόνο.")
    t_ar = TYPE_ACC[_known(chart, "Αφροδίτη", "Άρης").aspect]
    t_kr = TYPE_ACC[_known(chart, "Αφροδίτη", "Κρόνος").aspect]
    line = line.replace("τετράγωνο με τον Άρη", f"{t_ar} με τον Άρη").replace("τετράγωνο με τον Κρόνο", f"{t_kr} με τον Κρόνο")
    result = V.validate_analysis(chart, _add(good, line))
    assert result.ok, (line, result.details_lines()[:2])


def test_new_subject_in_same_sentence_wrong_is_caught(chart, good):
    subj = "Αφροδίτη"
    wrong = _unaspected_partner(chart, subj)
    t_ar = TYPE_ACC[_known(chart, "Αφροδίτη", "Άρης").aspect]
    line = (f"Η Σελήνη σχηματίζει τρίγωνο με τον Ερμή, η Αφροδίτη σχηματίζει "
            f"{t_ar} με τον Άρη και τετράγωνο με {ACC_ART[wrong]}.")
    result = V.validate_analysis(chart, _add(good, line))
    assert {frozenset((a, b)) for a, b, _, _ in result.undeclared_aspects} == {frozenset((subj, wrong))}, line


# 2. Πολλά αντικείμενα με κοινό τύπο όψης
@pytest.mark.parametrize(
    "tmpl, lang",
    [
        ("{S} σχηματίζει {t} με {o1} και {o2}.", "el"),
        ("{S} σχηματίζει {t} με {o1}, και {o2}.", "el"),
        ("{S} σε {t} με {o1} και {o2}, δίνει ευελιξία.", "el"),
        ("The {S} forms a {t} with {o1} and {o2}.", "en"),
    ],
)
@pytest.mark.parametrize("correct", [True, False])
def test_shared_aspect_type_with_two_objects(chart, tmpl, lang, correct):
    # Σελήνη: τρίγωνο με Ερμή και Αφροδίτη (και τα δύο υπάρχουν)
    a1, a2 = _known(chart, "Σελήνη", "Ερμής"), _known(chart, "Σελήνη", "Αφροδίτη")
    assert a1.aspect == a2.aspect
    second = "Αφροδίτη" if correct else _unaspected_partner(chart, "Σελήνη")
    if lang == "el":
        line = tmpl.format(S="Η Σελήνη", t=TYPE_ACC[a1.aspect], o1=ACC_ART["Ερμής"], o2=ACC_ART[second])
    else:
        line = tmpl.format(S=EN.en("Σελήνη"), t=EN.en(a1.aspect).lower(), o1=EN.en("Ερμής"), o2="the " + EN.en(second))
    result = V.validate_analysis(chart, _add(build_analysis(chart, lang), line))
    if correct:
        assert result.ok, (line, result.details_lines()[:2])
    else:
        assert {frozenset((a, b)) for a, b, _, _ in result.undeclared_aspects} == {frozenset(("Σελήνη", second))}, line


@pytest.mark.parametrize(
    "line",
    [
        # «και ο/η» = ΝΕΟ υποκείμενο, όχι δεύτερο αντικείμενο
        "Η Σελήνη σε τρίγωνο με τον Ερμή και ο Ήλιος στον Λέοντα δίνουν θέρμη.",
        "Η Σελήνη σχηματίζει τρίγωνο με τον Ερμή και η Αφροδίτη ακολουθεί.",
        # η φράση συνεχίζει μετά το δεύτερο όνομα: δεν είναι αντικείμενο της όψης
        "The Moon forms a trine with Mercury and the Sun shines in Leo.",
    ],
)
def test_coordinated_new_subject_is_not_an_object(chart, line):
    import validation_aspects as VA
    claims = {frozenset((a, b)) for a, b, *_ in VA._aspect_claims(line)}
    assert frozenset(("Σελήνη", "Ήλιος")) not in claims and frozenset(("Σελήνη", "Αφροδίτη")) not in claims, claims


# 3. Αυτοόψη σε κάθε μορφή
@pytest.mark.parametrize(
    "line, lang",
    [
        ("Ο Ήλιος σχηματίζει τετράγωνο με τον Ήλιο.", "el"),
        ("Ο Ήλιος σε τετράγωνο με τον Ήλιο.", "el"),
        ("Sun forms a square with Sun.", "en"),
        ("The Sun forms a square with the Sun.", "en"),
    ],
)
def test_self_aspect_fails(chart, line, lang):
    result = V.validate_analysis(chart, _add(build_analysis(chart, lang), line))
    assert not result.ok
    assert any(a == b for a, b, _, _ in result.undeclared_aspects), line


# ---------------------------------------------------------------------------
# Δέκατος γύρος (validator v13): κάθε μορφή σωστή ΚΑΙ λανθασμένη, el/en
# ---------------------------------------------------------------------------
SHARED_FORMS = [
    ("Η Σελήνη σχηματίζει {t} με τον Ερμή και με {o2}.", "el"),
    ("Η Σελήνη σχηματίζει {t} με τον Ερμή και {o2} στον γενέθλιο χάρτη.", "el"),
    ("Η Σελήνη σχηματίζει {t} με τον Ερμή καθώς και με {o2}.", "el"),
    ("The Moon forms a {t} with Mercury and with the {o2}.", "en"),
    ("The Moon forms a {t} with Mercury and the {o2} in the natal chart.", "en"),
    ("The Moon forms a {t} with Mercury as well as with the {o2}.", "en"),
]
ELLIPTIC_FORMS = [
    ("Η Σελήνη σχηματίζει {t} με τον Ερμή καθώς και {t} με {o2}.", "el"),
    ("Η Σελήνη σχηματίζει {t} με τον Ερμή, όπως και {t} με {o2}.", "el"),
    ("The Moon forms a {t} with Mercury as well as a {t} with the {o2}.", "en"),
]


@pytest.mark.parametrize("tmpl, lang", SHARED_FORMS + ELLIPTIC_FORMS)
@pytest.mark.parametrize("correct", [True, False])
def test_round10_forms(chart, tmpl, lang, correct):
    a1 = _known(chart, "Σελήνη", "Ερμής")
    assert _known(chart, "Σελήνη", "Αφροδίτη").aspect == a1.aspect
    second = "Αφροδίτη" if correct else _unaspected_partner(chart, "Σελήνη")
    if lang == "el":
        line = tmpl.format(t=TYPE_ACC[a1.aspect], o2=ACC_ART[second])
    else:
        line = tmpl.format(t=EN.en(a1.aspect).lower(), o2=EN.en(second))
    result = V.validate_analysis(chart, _add(build_analysis(chart, lang), line))
    if correct:
        assert result.ok, (line, result.details_lines()[:2])
    else:
        assert {frozenset((a, b)) for a, b, _, _ in result.undeclared_aspects} == {frozenset(("Σελήνη", second))}, line
