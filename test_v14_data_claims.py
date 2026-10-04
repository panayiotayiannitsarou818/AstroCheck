"""v14: δηλώσεις δεδομένων (θέση, ζώδιο, Οίκος, ακμή, κίνηση), φίλτρο
προσωπικών στοιχείων, έλεγχος όψεων/κυβερνητών στο τελικό έντυπο, και
αυτόματη διόρθωση από την καλύτερη απόπειρα."""

from pathlib import Path

import pytest

import validator as V
import validation_structure as VS
from generator import generate_validated
from parser import parse_astrodienst_pdf
from prompts import build_master_prompt
from test_english import build_analysis
from test_rewrite_content import _good

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("astro_paradeigma*.pdf"))
FIXTURE = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"


@pytest.fixture(scope="module")
def chart():
    return parse_astrodienst_pdf(FIXTURE.read_bytes(), FIXTURE.name)


def _with(chart, lang, sentence):
    lines = build_analysis(chart, lang).split("\n")
    return "\n".join(lines[:3] + [sentence] + lines[3:])


WRONG = [
    ("el", "Ο Ήλιος στο ζώδιο του Λέοντα φωτίζει τον Οίκο."),
    ("el", "Ο Ήλιος σε Λέοντα φωτίζει τον Οίκο."),
    ("el", "Με τον Ήλιο στον 7ο Οίκο οι σχέσεις γίνονται κεντρικές."),
    ("el", "Ο Άρης του 7ου Οίκου ζητά δράση."),
    ("el", "Ο Ήλιος βρίσκεται στις 15°00′ του Υδροχόου."),
    ("el", "Ήλιος: Υδροχόος 15°00′"),
    ("el", "Η ακμή του Οίκου βρίσκεται στον Σκορπιό."),
    ("el", "Ο 1ος Οίκος ξεκινά στον Λέοντα."),
    ("el", "Ο Άρης είναι ανάδρομος και ζητά αναθεώρηση."),
    ("el", "Ο ανάδρομος Άρης ζητά αναθεώρηση."),
    ("el", "Ο Κρόνος είναι ορθόδρομος."),
    ("en", "Mars is retrograde and asks for revision."),
    ("en", "The cusp of this House falls in Scorpio."),
]

RIGHT = [
    ("el", "Ο Ήλιος στο ζώδιο του Υδροχόου φωτίζει τον 3ο Οίκο."),
    ("el", "Με τον Ήλιο στον 3ο Οίκο η επικοινωνία γίνεται κεντρική."),
    ("el", "Η ακμή του Οίκου βρίσκεται στον Τοξότη και η επόμενη ακμή στον Αιγόκερω."),
    ("el", "Ο Κρόνος είναι ανάδρομος και ζητά αναθεώρηση."),
    ("el", "Ο ανάδρομος Κρόνος και ο Άρης βρίσκονται στον Ζυγό."),
    ("el", "Ο Άρης δεν είναι ανάδρομος."),
    ("el", "Η Σελήνη, κυβερνήτης του 8ου Οίκου, βρίσκεται στον 10ο Οίκο."),
    ("el", "Ο Κρόνος λειτουργεί εδώ σαν αυστηρός καθηγητής που ζητά συνέπεια."),
    ("el", "Υπάρχει κίνδυνος για επαγγελματική εξουθένωση όταν η πειθαρχία γίνεται υπερβολική."),
    ("el", "Η Σελήνη δείχνει πώς μπορεί να βιώνεις τη φροντίδα ως μητέρα ή ως παιδί."),
    ("en", "Saturn acts here like a strict teacher who asks for consistency."),
    ("en", "There is a risk of burnout when discipline becomes excessive."),
    ("en", "Saturn is retrograde and asks for revision."),
]


@pytest.mark.parametrize("lang,sentence", WRONG, ids=[s for _, s in WRONG])
def test_wrong_data_statement_is_rejected(chart, lang, sentence):
    assert not V.validate_analysis(chart, _with(chart, lang, sentence)).ok


@pytest.mark.parametrize("lang,sentence", RIGHT, ids=[s for _, s in RIGHT])
def test_true_statement_is_accepted(chart, lang, sentence):
    result = V.validate_analysis(chart, _with(chart, lang, sentence))
    assert result.ok, result.details_lines()


@pytest.mark.parametrize(
    "sentence",
    [
        "Είσαι καθηγήτρια και αυτό φαίνεται στον χάρτη.",
        "Ως μητέρα δύο παιδιών κουβαλάς ευθύνη.",
        "Η επαγγελματική σου εξουθένωση συνδέεται με τον Κρόνο.",
        "As a teacher, you have two children to care for.",
    ],
)
def test_explicit_personal_statements_are_still_caught(sentence):
    assert VS._unauthorized_personal_claims({}, sentence)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_checked_data_of_the_prompt_never_trips_the_data_checks(path):
    """Οι θέσεις/κινήσεις όπως ακριβώς τις δίνει η εντολή είναι σωστές: αν το
    μοντέλο τις αντιγράψει αυτούσιες, δεν πρέπει να απορριφθούν."""
    c = parse_astrodienst_pdf(path.read_bytes(), path.name)
    prompt = build_master_prompt(c, {}, "Ελληνικά", "", "")
    data = prompt.split("ΕΛΕΓΜΕΝΑ ΔΕΔΟΜΕΝΑ ΑΝΑ ΟΙΚΟ")[1].split("ΤΕΛΙΚΕΣ ΥΠΟΧΡΕΩΤΙΚΕΣ ΕΝΟΤΗΤΕΣ")[0]
    assert VS._data_claim_errors(c, data) == []
    assert VS._sign_claim_errors(c, data) == []
    assert VS._location_claim_errors(c, data) == []


# --- τελικό έντυπο πελάτη ----------------------------------------------------
REWRITE_WRONG = [
    "Η Σελήνη σχηματίζει τετράγωνο με τον Κρόνο και αυτό φέρνει βάρος.",
    "Ο Ήλιος βρίσκεται σε αντίθεση με τον Άρη.",
    "Ο Άρης είναι ανάδρομος.",
    "Κύριος κυβερνήτης του Οίκου είναι η Αφροδίτη.",
]


def _rewrite_with(chart, sentence):
    lines = _good(chart).split("\n")
    return "\n".join(lines[:2] + [sentence] + lines[2:])


@pytest.mark.parametrize("sentence", REWRITE_WRONG)
def test_client_document_rejects_statements_absent_from_chart(chart, sentence):
    source = build_analysis(chart, "el")
    result = V.validate_rewrite(chart, source, _rewrite_with(chart, sentence))
    assert not result.ok and result.details_lines()


@pytest.mark.parametrize(
    "sentence",
    [
        "Η Σελήνη σχηματίζει τετράγωνο με τον Ποσειδώνα και αυτό φέρνει ευαισθησία.",
        "Ο Κρόνος, σε σύνοδο με τον Άρη, σχηματίζει εξάγωνο με τον Ποσειδώνα.",
        "Κύριος κυβερνήτης του Οίκου είναι ο Δίας.",
        "Ο Κρόνος είναι ανάδρομος.",
    ],
)
def test_client_document_accepts_true_statements(chart, sentence):
    source = build_analysis(chart, "el")
    result = V.validate_rewrite(chart, source, _rewrite_with(chart, sentence))
    assert result.ok, result.details_lines()


# --- αυτόματη διόρθωση -------------------------------------------------------
def test_revision_starts_from_the_best_attempt():
    class Result:
        def __init__(self, n):
            self.n, self.ok = n, False

        def summary(self):
            return ""

        def details_lines(self):
            return ["σφάλμα"] * self.n

    errors = {"A": 2, "B": 9, "C": 5}
    outputs, inputs = iter("ABC"), []

    def complete(key, text, model):
        inputs.append(text)
        return next(outputs)

    outcome = generate_validated("k", "ΕΝΤΟΛΗ", lambda t: Result(errors[t]), complete=complete)
    assert inputs[2].rstrip().endswith("A")  # ο 3ος γύρος διορθώνει το A, όχι το χειρότερο B
    assert outcome.text == "A"
