"""v16: διαχωρισμός Οίκων, ύστερα από δύο πραγματικές απορρίψεις (χάρτης «A.M.»):

1. Λίστα «1ος Οίκος … 12ος Οίκος» στην αρχή (πίνακας ακμών) «άνοιγε» όλους τους
   Οίκους μέσα στη λίστα και όλο το κείμενο αποδιδόταν στον 12ο.
2. Ο 12ος Οίκος έφτανε ως το τέλος του κειμένου: οι κυβερνήτες του Βόρειου
   Δεσμού στη «Συμβολική κατεύθυνση εξέλιξης» διαβάζονταν ως κυβερνήτες του 12ου.
"""
import validator as V
from generator import build_rewrite_prompt

HOUSES = "\n".join(f"{n}ος Οίκος — Θέμα {n}\nΚείμενο Οίκου {n}." for n in range(1, 13))
TAIL = "\nΤελική συνθετική εικόνα\nΣύνθεση.\nΣυμβολική κατεύθυνση εξέλιξης\nΟ Ουρανός και ο Κρόνος.\n"


def test_twelfth_house_ends_before_the_final_sections():
    seg = V._house_segments(HOUSES + TAIL)
    assert seg[12].strip().endswith("Κείμενο Οίκου 12.")
    assert "Ουρανός" not in seg[12]


def test_alternative_final_heading_also_closes_the_twelfth_house():
    text = HOUSES + "\nΤελική σύνθεση\nΚάτι για τον Κρόνο.\n"
    assert "Κρόνο" not in V._house_segments(text)[12]


def test_a_mention_in_prose_does_not_cut_the_twelfth_house():
    text = HOUSES + " Αυτό θα φανεί στη συμβολική κατεύθυνση εξέλιξης του χάρτη. Συνέχεια 12ου." + TAIL
    assert "Συνέχεια 12ου." in V._house_segments(text)[12]


def test_list_of_houses_before_the_real_headings_is_skipped():
    cusps = "Ακμές των Οίκων\n" + "\n".join(f"{n}ος Οίκος\nΔίδυμοι" for n in range(1, 13)) + "\n"
    seg = V._house_segments("Εισαγωγή\n" + cusps + "Μεθοδολογία\n" + HOUSES + TAIL)
    assert sorted(seg) == list(range(1, 13))
    for n in range(1, 13):
        assert f"Κείμενο Οίκου {n}." in seg[n]


def test_table_row_inside_the_first_house_does_not_move_the_start():
    text = HOUSES.replace("Κείμενο Οίκου 1.", "Κείμενο Οίκου 1.\n1ος Οίκος | Τοξότης | 3°12′") + TAIL
    assert V._house_segments(text)[1].startswith("1ος Οίκος — Θέμα 1")


def test_rewrite_prompt_asks_for_quincunx_without_degrees():
    command = "Η εντολή\nΚανόνες.\nΗμερολόγιο διορθώσεων ανά ανάλυση\nΥΠΟΧΡΕΩΤΙΚΟΣ ΤΕΛΙΚΟΣ ΕΛΕΓΧΟΣ ΑΜΕΤΑΒΛΗΤΩΝ ΔΕΔΟΜΕΝΩΝ\nΈλεγχος."
    prompt = build_rewrite_prompt(command, "ανάλυση", "A.M.", "")
    assert "«χιαστί όψη»" in prompt and "χωρίς τον αριθμό «150°»" in prompt


# --- v16.1: σκέτος «κυβερνήτης» του ίδιου Οίκου στο τελικό έντυπο ----------
def test_bare_ruler_phrases_of_the_same_house_are_recognised():
    from validation_structure import _ruler_claims_in_body
    for s in ["Ο Άρης είναι ο κυβερνήτης αυτού του Οίκου.", "Ο κυβερνήτης του Οίκου είναι ο Άρης.",
              "Κυβερνήτης του 1ου Οίκου είναι ο Άρης.", "The ruler of this House is Mars."]:
        assert ("Άρης", "κυβερνήτης") in _ruler_claims_in_body(s, 1), s


def test_ruler_phrases_about_another_house_are_not_claims_for_this_one():
    from validation_structure import _ruler_claims_in_body
    for s in ["Ο Κρόνος, κυβερνήτης του 8ου Οίκου, βρίσκεται εδώ.",
              "Η Αφροδίτη, κυβερνήτης του Οίκου της οικειότητας, συνδέεται."]:
        assert not any(r == "κυβερνήτης" for _, r in _ruler_claims_in_body(s, 1)), s
