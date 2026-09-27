"""Το έντυπο πελάτη δεν περνά αν είναι ουσιαστικά άδειο.

Αφορμή (κριτική v10): ένα «έντυπο» με ΜΟΝΟ τους 12 τίτλους Οίκων πέρασε τον
έλεγχο. Τώρα απαιτείται ουσιαστικό κείμενο ανά Οίκο και ενότητα,
«Κεντρικό θέμα:» ανά Οίκο (κανόνας 15) και κατονομασία κάθε πλανήτη στον
Οίκο του (κανόνας 7).
"""

from pathlib import Path

import pytest

import lexicon_en as EN
import validator as V
from parser import parse_astrodienst_pdf
from sample_texts import FILLER_EL, houses_el, houses_en, section_body
from test_english import build_analysis

SECTIONS = ["Τελική συνθετική εικόνα", "Συμβολική κατεύθυνση εξέλιξης", "Προτάσεις προσωπικής ανάπτυξης"]


@pytest.fixture(scope="module")
def chart():
    path = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"
    return parse_astrodienst_pdf(path.read_bytes(), path.name)


@pytest.fixture(scope="module")
def source(chart):
    return build_analysis(chart, "el")


def _good(chart, houses=None):
    houses = houses if houses is not None else houses_el(chart)
    return houses + "\n" + "\n".join(f"{s}\n{section_body()}" for s in SECTIONS)


def test_complete_client_document_passes(chart, source):
    r = V.validate_rewrite(chart, source, _good(chart))
    assert r.ok, r.details_lines()


def test_headings_only_document_is_rejected(chart, source):
    """Το ακριβές περιστατικό της κριτικής."""
    empty = "\n".join(f"{n}ος Οίκος" for n in range(1, 13))
    r = V.validate_rewrite(chart, source, empty)
    assert not r.ok
    assert [n for n, _, _ in r.thin_houses] == list(range(1, 13))
    assert r.houses_without_theme == list(range(1, 13))


def test_headings_and_section_titles_only_is_rejected(chart, source):
    empty = "\n".join(f"{n}ος Οίκος" for n in range(1, 13)) + "\n" + "\n".join(SECTIONS)
    r = V.validate_rewrite(chart, source, empty)
    assert not r.ok
    assert {s for s, _ in r.empty_sections} == set(SECTIONS)


def test_one_thin_house_is_named(chart, source):
    text = _good(chart)
    seg = text[text.index("5ος Οίκος") : text.index("6ος Οίκος")]
    thin = "5ος Οίκος\nΚεντρικό θέμα: η χαρά."
    r = V.validate_rewrite(chart, source, text.replace(seg, thin + "\n"))
    assert [n for n, _, _ in r.thin_houses] == [5]


def test_missing_central_theme_is_caught(chart, source):
    text = _good(chart)
    seg = text[text.index("7ος Οίκος") : text.index("8ος Οίκος")]
    r = V.validate_rewrite(chart, source, text.replace(seg, seg.replace("Κεντρικό θέμα:", "Συνοψίζοντας,")))
    assert r.houses_without_theme == [7] and not r.ok


def test_planet_not_named_in_its_house_is_caught(chart, source):
    moon = next(p for p in chart.points if p.name == "Σελήνη")
    text = _good(chart)
    heading = f"{moon.house}ος Οίκος"
    nxt = f"{moon.house + 1}ος Οίκος" if moon.house < 12 else SECTIONS[0]
    seg = text[text.index(heading) : text.index(nxt)]
    r = V.validate_rewrite(chart, source, text.replace(seg, seg.replace("Σελήνη", "συναισθηματική φύση")))
    assert (moon.house, "Σελήνη") in r.unnamed_planets and not r.ok


def test_house_much_shorter_than_source_is_caught(chart):
    long_source = "\n".join(
        f"{n}ος Οίκος\n" + (FILLER_EL + "\n") * (10 if n == 3 else 1) for n in range(1, 13)
    )
    r = V.validate_rewrite(chart, long_source, _good(chart))
    assert [n for n, _, _ in r.thin_houses] == [3]


def test_technical_lines_of_source_do_not_inflate_the_requirement(chart, source):
    """Οι γραμμές όψεων με orb και το πλαίσιο σύνοψης της πηγής δεν μετράνε."""
    assert V.validate_rewrite(chart, source, _good(chart)).thin_houses == []


def test_twelfth_house_does_not_borrow_final_sections(chart, source):
    text = _good(chart)
    seg12 = text[text.index("12ος Οίκος") : text.index(SECTIONS[0])]
    r = V.validate_rewrite(chart, source, text.replace(seg12, "12ος Οίκος\n"))
    assert 12 in [n for n, _, _ in r.thin_houses]


def test_english_client_document_needs_central_theme(chart):
    src = build_analysis(chart, "en")
    good = houses_en(chart) + "\n" + "\n".join(
        f"{t}\n{section_body('en')}" for t in list(EN.SECTION_TITLES.values())[:3]
    )
    assert V.validate_rewrite(chart, src, good).ok
    r = V.validate_rewrite(chart, src, good.replace("Central theme:", "In short,", 1))
    assert r.houses_without_theme == [1]


def test_success_message_does_not_overclaim(chart, source):
    msg = V.validate_rewrite(chart, source, _good(chart)).summary()
    assert "ΔΕΝ ελέγχεται μηχανικά" in msg and "ανάγνωση" in msg
    assert "Δεν είναι έγκριση της ερμηνείας" in msg


# ---------------------------------------------------------------------------
# Κριτική v11: η ίδια γενική παράγραφος σε όλους τους Οίκους
# ---------------------------------------------------------------------------
def _same_paragraph_everywhere(chart, paragraph):
    from sample_texts import house_body

    parts = []
    for n in range(1, 13):
        names = house_body(n, chart).split(". ")[0] if "Εδώ έχουν βάρος" in house_body(n, chart) else ""
        parts.append(f"{n}ος Οίκος\n{names + '. ' if names else ''}{paragraph}\nΚεντρικό θέμα: θέμα {n}.")
    return "\n".join(parts) + "\n" + "\n".join(f"{s}\n{section_body()}" for s in SECTIONS)


def test_same_generic_paragraph_in_every_house_is_rejected(chart, source):
    """Το ακριβές περιστατικό της κριτικής v11."""
    r = V.validate_rewrite(chart, source, _same_paragraph_everywhere(chart, FILLER_EL))
    assert not r.ok
    assert r.repeated_text and set(r.repeated_text[0][0]) == set(range(1, 13))


def test_same_paragraph_with_swapped_planet_names_is_still_caught(chart, source):
    text = _good(chart)
    seg3 = text[text.index("3ος Οίκος") : text.index("4ος Οίκος")]
    seg4 = text[text.index("4ος Οίκος") : text.index("5ος Οίκος")]
    copy = seg3.replace("3ος Οίκος", "4ος Οίκος")
    for p in chart.points:  # ίδιο κείμενο, αλλά με τα ονόματα του 4ου Οίκου
        if p.house == 4 and p.name not in copy:
            copy = copy.replace("Κεντρικό θέμα:", f"{p.name}. Κεντρικό θέμα:", 1)
    r = V.validate_rewrite(chart, source, text.replace(seg4, copy))
    assert any(set(g) == {3, 4} for g, _ in r.repeated_text)


def test_lightly_paraphrased_copy_is_caught(chart, source):
    text = _good(chart)
    base = FILLER_EL
    varied = base.replace("χρόνο", "λίγο χρόνο").replace("ισορροπία", "μια ισορροπία")
    seg2 = text[text.index("2ος Οίκος") : text.index("3ος Οίκος")]
    seg9 = text[text.index("9ος Οίκος") : text.index("10ος Οίκος")]
    text = text.replace(seg2, seg2.replace("Κεντρικό θέμα:", base + "\nΚεντρικό θέμα:"))
    text = text.replace(seg9, seg9.replace("Κεντρικό θέμα:", varied + "\nΚεντρικό θέμα:"))
    r = V.validate_rewrite(chart, source, text)
    assert any(set(g) == {2, 9} for g, _ in r.repeated_text)


def test_short_common_phrases_are_allowed(chart, source):
    """Σύντομες κοινές φράσεις (κάτω από 8 λέξεις) δεν μετρούν ως επανάληψη."""
    text = _good(chart).replace("Κεντρικό θέμα:", "Το ζητούμενο εδώ είναι η ισορροπία. Κεντρικό θέμα:")
    assert V.validate_rewrite(chart, source, text).repeated_text == []


def test_simple_house_can_stay_short(chart):
    """Κανόνας 18: ένας απλός Οίκος δεν χρειάζεται τεχνητή επιμήκυνση."""
    assert V.MIN_HOUSE_WORDS <= 30


# ---------------------------------------------------------------------------
# Κριτική v12: μία κοινή πρόταση δεν πρέπει να κλειδώνει τη λήψη
# ---------------------------------------------------------------------------
COMMON = "Το ζητούμενο εδώ είναι να βρεις ισορροπία ανάμεσα στην ασφάλεια και στην εξέλιξη."


def _add_to_house(text, n, extra):
    nxt = f"{n + 1}ος Οίκος" if n < 12 else SECTIONS[0]
    seg = text[text.index(f"{n}ος Οίκος") : text.index(nxt)]
    return text.replace(seg, seg.replace("Κεντρικό θέμα:", extra + "\nΚεντρικό θέμα:"))


def test_one_shared_sentence_only_warns(chart, source):
    text = _add_to_house(_add_to_house(_good(chart), 3, COMMON), 8, COMMON)
    r = V.validate_rewrite(chart, source, text)
    assert r.ok, r.details_lines()
    assert r.repeated_text == []
    assert len(r.warnings) == 1 and "3ο" in r.warnings[0] and "8ο" in r.warnings[0]


def test_one_shared_sentence_in_many_houses_still_only_warns(chart, source):
    text = _good(chart)
    for n in (2, 5, 9):
        text = _add_to_house(text, n, COMMON)
    r = V.validate_rewrite(chart, source, text)
    assert r.ok and len(r.warnings) == 1  # ΜΙΑ ομαδοποιημένη προειδοποίηση
    assert "3 Οίκους" in r.warnings[0] and "2ο, 5ο, 9ο" in r.warnings[0]


def test_two_shared_sentences_forming_most_of_the_house_block(chart, source):
    second = "Όταν δίνεις χρόνο στον εαυτό σου, οι αποφάσεις σου γίνονται πιο καθαρές και πιο δικές σου."
    text = _good(chart)
    for n in (4, 10):
        text = _add_to_house(text, n, COMMON + " " + second)
    r = V.validate_rewrite(chart, source, text)
    assert not r.ok and any(set(g) == {4, 10} for g, _ in r.repeated_text)


# ---------------------------------------------------------------------------
# Κριτική v14: μία μεγάλη πρόταση-παράγραφος σε όλους τους Οίκους
# ---------------------------------------------------------------------------
LONG_ONE_SENTENCE = (
    "Σε αυτόν τον τομέα της ζωής σου μπορεί να χρειάζεσαι χρόνο, υπομονή και χώρο για να "
    "εμπιστευτείς τις ανάγκες σου, να ακούσεις τι σε κρατά πίσω και να επιτρέψεις στον εαυτό "
    "σου να προχωρήσει με τον δικό του ρυθμό χωρίς πίεση"
)  # ≈ 38 λέξεις, ΜΙΑ πρόταση


def test_long_single_sentence_paragraph_in_all_houses_is_rejected(chart, source):
    """Το ακριβές περιστατικό της κριτικής v14."""
    r = V.validate_rewrite(chart, source, _same_paragraph_everywhere(chart, LONG_ONE_SENTENCE + "."))
    assert not r.ok
    assert len(r.repeated_text) == 1 and set(r.repeated_text[0][0]) == set(range(1, 13))
    assert r.warnings == []  # όχι 66 προειδοποιήσεις


def test_long_copied_sentence_in_two_houses_is_rejected(chart, source):
    text = _good(chart)
    for n in (6, 11):
        text = _add_to_house(text, n, LONG_ONE_SENTENCE + ".")
    r = V.validate_rewrite(chart, source, text)
    assert not r.ok and any(set(g) == {6, 11} for g, _ in r.repeated_text)


def test_long_sentence_that_is_small_part_of_rich_houses_only_warns(chart):
    """Η ίδια μεγάλη πρόταση σε δύο πλούσιους Οίκους (μικρό μέρος τους) → προειδοποίηση."""
    long_source = "\n".join(f"{n}ος Οίκος\n" + (FILLER_EL + "\n") for n in range(1, 13))
    text = _good(chart)
    unique = {
        6: "Η φροντίδα του σώματος γίνεται για σένα τρόπος να ηρεμεί και ο νους. Όταν οργανώνεις "
        "τη μέρα σου με μέτρο, νιώθεις ότι ελέγχεις όσα σε αγχώνουν. Οι μικρές τελετουργίες της "
        "πρωίας σε βοηθούν να ξεκινάς με καθαρό κεφάλι. Η συνέπεια στα καθημερινά σού δίνει "
        "σιγουριά χωρίς να σε φυλακίζει.",
        11: "Οι παρέες που σε εμπνέουν είναι εκείνες που τολμούν να ονειρεύονται μαζί σου. Σε "
        "συλλογικές προσπάθειες βρίσκεις έναν ρόλο που σου ταιριάζει φυσικά. Τα όνειρα για το "
        "αύριο αποκτούν σχήμα όταν τα λες δυνατά σε φίλους. Η αίσθηση του ανήκειν σε κάνει πιο "
        "γενναιόδωρο με τον εαυτό σου.",
    }
    for n in (6, 11):
        text = _add_to_house(text, n, LONG_ONE_SENTENCE + ". " + unique[n])
    r = V.validate_rewrite(chart, long_source, text)
    assert not any(set(g) == {6, 11} for g, _ in r.repeated_text), r.repeated_text
    assert any("6ο" in w and "11ο" in w for w in r.warnings)
