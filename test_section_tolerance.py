"""Ισοδύναμοι τίτλοι ενοτήτων γίνονται δεκτοί· απλές αναφορές μέσα στο
κείμενο δεν «μετράνε» ως ενότητα· ενότητα που λείπει εντοπίζεται ακόμη."""

import pytest

import validator as V

S_SYN, S_DIR, S_TIPS, S_APP = (
    "Τελική συνθετική εικόνα",
    "Συμβολική κατεύθυνση εξέλιξης",
    "Προτάσεις προσωπικής ανάπτυξης",
    "Παράρτημα επιβεβαιωμένων όψεων",
)


@pytest.mark.parametrize(
    "section,heading",
    [
        (S_SYN, "Τελική σύνθεση"),
        (S_SYN, "## Συνολική εικόνα"),
        (S_SYN, "Τελική συνθετική εικόνα"),
        (S_DIR, "Ο άξονας των Δεσμών"),
        (S_DIR, "Κατεύθυνση εξέλιξης"),
        (S_DIR, "Βόρειος και Νότιος Δεσμός"),
        (S_TIPS, "3. Προτάσεις για την προσωπική εξέλιξη"),
        (S_TIPS, "Πρακτικές προτάσεις αυτογνωσίας"),
        (S_TIPS, "Προτάσεις προσωπικής ανάπτυξης και υποστήριξης"),
        (S_APP, "Τεχνικό παράρτημα"),
        (S_APP, "Πίνακας επιβεβαιωμένων όψεων"),
        (S_APP, "Παράρτημα"),
    ],
)
def test_equivalent_headings_are_accepted(section, heading):
    assert V._has_section(f"Εισαγωγή.\n{heading}\nΚείμενο ενότητας.", section)


@pytest.mark.parametrize(
    "section,sentence",
    [
        (S_DIR, "Αυτή η κατεύθυνση εξέλιξης φαίνεται σε πολλούς Οίκους και σε άλλα σημεία."),
        (S_APP, "Τα τεχνικά στοιχεία βρίσκονται στο τεχνικό παράρτημα του εντύπου σου εδώ."),
        (S_SYN, "Η τελική σύνθεση όλων αυτών δίνει μια εικόνα ισορροπίας στη ζωή σου."),
    ],
)
def test_mentions_inside_prose_do_not_count(section, sentence):
    assert not V._has_section(f"Κείμενο.\n{sentence}\nΤέλος.", section)


def test_house_heading_in_words_is_recognised():
    text = "Έβδομος Οίκος — Σχέσεις\nΚείμενο.\nΌγδοος Οίκος\nΚείμενο."
    assert V._HOUSE_HEADING_PATTERNS[6].search(text) and V._HOUSE_WORD_PATTERNS[7].search(text)
    assert not V._HOUSE_WORD_PATTERNS[9].search("Ενδέκατος Οίκος")  # «Δέκατος» ≠ «Ενδέκατος»


def test_appendix_starts_at_its_heading_not_at_first_mention():
    text = (
        "Μεθοδολογία: οι όψεις συγκεντρώνονται στο Παράρτημα στο τέλος.\n"
        "1ος Οίκος\nΚείμενο.\nΤεχνικό παράρτημα\nΉλιος–Κρόνος Τρίγωνο 0°14′"
    )
    assert V._find_appendix(text).startswith("Τεχνικό παράρτημα")


def test_rewrite_may_rename_sections():
    houses = "\n".join(f"{n}ος Οίκος\nΚείμενο." for n in range(1, 13))
    source = f"{houses}\n{S_SYN}\nα\n{S_DIR}\nβ\n{S_TIPS}\nγ\n{S_APP}\nδ"
    from models import Chart
    from sample_texts import houses_el, section_body

    body = section_body()
    rewrite = (
        f"{houses_el()}\nΤελική σύνθεση\n{body}\nΟ άξονας των Δεσμών\n{body}\n"
        f"Προτάσεις για την προσωπική εξέλιξη\n{body}"
    )

    r = V.validate_rewrite(Chart(), source, rewrite)
    assert r.ok, r.details_lines()
