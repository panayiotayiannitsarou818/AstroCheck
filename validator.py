"""
validator.py
=============
Ελέγχει το ΤΕΛΙΚΟ κείμενο ανάλυσης (πριν γίνει Word) ενάντια στο ελεγμένο
Chart -- δεν εμπιστεύεται ότι το μοντέλο ακολούθησε τις οδηγίες, το
επαληθεύει μηχανικά. Αυτό είναι το ίδιο ακριβώς λάθος που παρατηρήθηκε
χειροκίνητα (παρέλειψη όψεων παρά τις ρητές οδηγίες) -- ο σκοπός αυτού του
module είναι να μην ξαναπεράσει αθόρυβα.

v2: δύο προσθήκες, ύστερα από δύο συγκεκριμένα περιστατικά που η v1 δεν θα
είχε πιάσει:
  1. Ο μηχανικός έλεγχος κάλυπτε μόνο "Τετράγωνο"/"Αντίθεση". Μια σύνοδος με
     τον Ωροσκόπο ή το Μεσουράνημα (π.χ. Χείρωνας–Ωροσκόπος) δεν ελεγχόταν
     καθόλου, άρα η απουσία της δεν θα εμφανιζόταν ποτέ ως σφάλμα. Τώρα ο
     ορισμός του "mandatory" περιλαμβάνει και κάθε σύνοδο όπου συμμετέχει
     γωνία (astrology.OPPOSITE_ANGLE).
  2. Ο παλιός έλεγχος co-occurrence δεχόταν μια όψη ως "καλυμμένη" αν
     εμφανιζόταν ΟΠΟΥΔΗΠΟΤΕ στο κείμενο -- π.χ. μια όψη του κυβερνήτη ενός
     Οίκου που αναφέρεται μόνο στον Οίκο όπου φυσικά βρίσκεται ο πλανήτης,
     αλλά ποτέ στον Οίκο που ο ίδιος πλανήτης κυβερνά, περνούσε ως OK. Τώρα
     γίνεται ξεχωριστός έλεγχος ανά Οίκο (κανόνας 6Β): κάθε mandatory όψη
     πρέπει να εμφανίζεται μέσα στο τμήμα κειμένου κάθε Οίκου όπου το σημείο
     της είναι "involved" -- Οίκος-κατοικίας ΚΑΙ κάθε Οίκος που κυβερνά.

v3: νέος έλεγχος, ύστερα από συγκεκριμένο περιστατικό (ΠΑΝΑΓΙΩΤΑ, 9ος Οίκος)
που κανένας από τους παραπάνω ελέγχους δεν θα είχε πιάσει: το πλαίσιο
σύνοψης ("Κυβερνήτης: ...") ενός Οίκου είχε αντιγραφεί αυτούσιο από άλλον
Οίκο, ενώ το κυρίως κείμενο του ίδιου Οίκου ονόμαζε σωστά διαφορετικό
πλανήτη ως κυβερνήτη. Ούτε ο έλεγχος όψεων ούτε ο έλεγχος ενοτήτων το
εντοπίζουν, γιατί το λάθος όνομα είναι έγκυρο αστρολογικό όνομα, απλώς για
λάθος Οίκο. Τώρα, για κάθε Οίκο, εξάγεται ο κυβερνήτης (ή οι κυβερνήτες,
όταν δηλώνονται και σύγχρονος και παραδοσιακός) από την εισαγωγική πρόταση
του κυρίως κειμένου, και ελέγχεται ότι το ίδιο όνομα εμφανίζεται μέσα στη
γραμμή "Κυβερνήτης:" του πλαισίου σύνοψης του ΙΔΙΟΥ Οίκου.

Η λήψη του τελικού Word πρέπει να παραμένει κλειδωμένη όσο
ValidationResult.ok είναι False.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from astrology import RULERS, OPPOSITE_ANGLE

REQUIRED_SECTIONS = [
    "Τελική συνθετική εικόνα",
    "Συμβολική κατεύθυνση εξέλιξης",
    "Προτάσεις προσωπικής ανάπτυξης",
    "Παράρτημα επιβεβαιωμένων όψεων",
]

# Κανονικοποίηση των συνηθέστερων ελληνικών πτώσεων. Ο παλιός validator
# έψαχνε μόνο την ονομαστική (π.χ. «Πλούτωνας») και απέρριπτε σωστές φράσεις
# όπως «με τον Πλούτωνα» ή «του Κρόνου».
_NAME_FORMS = {
    "Ήλιος": r"Ήλι(?:ος|ο|ου)",
    "Σελήνη": r"Σελήν(?:η|ης)",
    "Ερμής": r"Ερμ(?:ής|ή)",
    "Αφροδίτη": r"Αφροδίτ(?:η|ης)",
    "Άρης": r"Άρ(?:ης|η)",
    "Δίας": r"Δί(?:ας|α)",
    "Κρόνος": r"Κρόν(?:ος|ο|ου)",
    "Ουρανός": r"Ουραν(?:ός|ό|ού)",
    "Ποσειδώνας": r"Ποσειδών(?:ας|α)",
    "Πλούτωνας": r"Πλούτων(?:ας|α)",
    "Βόρειος Δεσμός": r"Βόρει(?:ος|ο|ου)\s+Δεσμ(?:ός|ό|ού)",
    "Νότιος Δεσμός": r"Νότι(?:ος|ο|ου)\s+Δεσμ(?:ός|ό|ού)",
    "Χείρωνας": r"Χείρων(?:ας|α)",
    "Ωροσκόπος": r"Ωροσκόπ(?:ος|ο|ου)",
    "Μεσουράνημα": r"Μεσουρ(?:άνημα|ανήματος)",
}

_ASPECT_FORMS = {
    "Σύνοδος": r"σύνοδ(?:ος|ο|ου)",
    "Εξάγωνο": r"εξάγων(?:ο|ου)",
    "Τετράγωνο": r"τετράγων(?:ο|ου)",
    "Τρίγωνο": r"τρίγων(?:ο|ου)",
    "Αντίθεση": r"αντίθεσ(?:η|ης)",
    "Χιαστί όψη 150°": r"χιαστί(?:\s+όψη)?(?:\s+150°)?",
}

_WEIGHT_FORMS = {
    "Στενή/ισχυρή": r"στεν(?:ή|ό)\s*/\s*ισχυρ(?:ή|ό)",
    "Κανονική": r"κανονικ(?:ή|ό)",
    "Πλατιά αλλά έγκυρη": r"πλατ(?:ιά|ύ)\s+αλλά\s+έγκυρ(?:η|ο)",
    "Πολύ πλατιά/δευτερεύουσα": r"πολύ\s+πλατ(?:ιά|ύ)\s*/\s*δευτερεύ(?:ουσα|ον)",
}

ANGLE_NAMES = set(OPPOSITE_ANGLE.keys())  # {"Ωροσκόπος", "Μεσουράνημα"}

_HOUSE_PATTERNS = [
    re.compile(rf"\b{n}ος\s+Ο[ιί]κ", re.IGNORECASE) for n in range(1, 13)
]
# Εναλλακτική διατύπωση: "Οίκος 7", "ΟΙΚΟΣ 7"
_HOUSE_PATTERNS_ALT = [
    re.compile(rf"Ο[ιί]κ\w*\s+{n}\b") for n in range(1, 13)
]
_HOUSE_HEADING_PATTERNS = [
    re.compile(rf"(?im)^\s*(?:#{{1,3}}\s*)?{n}ος\s+Ο[ιί]κ\w*\b")
    for n in range(1, 13)
]

_WINDOW = 350  # χαρακτήρες γύρω από κάθε εμφάνιση ονόματος, για αναζήτηση ταιριάσματος

# v3: εντοπίζει "Κύριος (σύγχρονος) κυβερνήτης είναι ο/η <Χ>" και, σε
# ξεχωριστή πρόταση, "Παραδοσιακός κυβερνήτης είναι ο/η <Χ>" -- ακριβώς η
# διατύπωση που ήδη χρησιμοποιεί η πρόζα των τελικών αναλύσεων.
_RULER_INTRO_PATTERNS = [
    re.compile(r"Κύριος(?:\s+σύγχρονος)?(?:\s*/\s*κύριος)?\s+κυβερνήτης\s+είναι\s+(?:ο|η)\s+(\S+)", re.IGNORECASE),
    re.compile(r"Παραδοσιακός\s+κυβερνήτης\s+είναι\s+(?:ο|η)\s+(\S+)", re.IGNORECASE),
]
# Η γραμμή του πλαισίου σύνοψης, μέχρι το τέλος της γραμμής.
_BOX_RULER_LINE = re.compile(r"Κυβερνήτης\s*[:\-]\s*(.+)")

_SECTION_PATTERNS = {
    "Τελική συνθετική εικόνα": r"Τελική\s+συνθετική\s+εικόνα",
    "Συμβολική κατεύθυνση εξέλιξης": r"Συμβολική\s+κατεύθυνση\s+εξέλιξης",
    "Προτάσεις προσωπικής ανάπτυξης": r"Προτάσεις\s+προσωπικής\s+ανάπτυξης",
    "Παράρτημα επιβεβαιωμένων όψεων": r"Παράρτημα[^\r\n]{0,90}επιβεβαιωμέν\w*[^\r\n]{0,40}όψε(?:ων|ις)",
}


@dataclass
class ValidationResult:
    ok: bool
    missing_houses: list = field(default_factory=list)
    missing_aspects: list = field(default_factory=list)      # εντελώς απούσες, πουθενά στο κείμενο
    suspect_aspects: list = field(default_factory=list)      # ονόματα υπάρχουν, orb όχι κοντά
    missing_from_appendix: list = field(default_factory=list)
    missing_sections: list = field(default_factory=list)
    missing_per_house: list = field(default_factory=list)    # (house_number, aspect) -- κανόνας 6Β
    wrong_aspect_type: list = field(default_factory=list)
    wrong_weight: list = field(default_factory=list)
    inconsistent_ruler_box: list = field(default_factory=list)  # (house_number, expected_names, box_text)
    wrong_house_claims: list = field(default_factory=list)
    unauthorized_personal_claims: list = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "✓ Η ανάλυση φαίνεται πλήρης: όλα τα υποχρεωτικά στοιχεία εντοπίστηκαν στο κείμενο, σε κάθε Οίκο που έπρεπε."
        parts = []
        if self.missing_houses:
            parts.append(f"{len(self.missing_houses)} Οίκοι δεν εντοπίστηκαν ({', '.join(map(str, self.missing_houses))})")
        if self.missing_aspects:
            parts.append(f"{len(self.missing_aspects)} υποχρεωτικές όψεις (τετράγωνα/αντιθέσεις/σύνοδοι με γωνία) λείπουν εντελώς")
        if self.suspect_aspects:
            parts.append(f"{len(self.suspect_aspects)} όψεις με ύποπτο ή απόν orb")
        if self.missing_from_appendix:
            parts.append(f"{len(self.missing_from_appendix)} όψεις δεν εντοπίστηκαν στο Παράρτημα")
        if self.missing_sections:
            parts.append(f"λείπουν οι ενότητες: {', '.join(self.missing_sections)}")
        if self.missing_per_house:
            parts.append(f"{len(self.missing_per_house)} όψεις κυβερνήτη λείπουν από συγκεκριμένο Οίκο (κανόνας 6Β)")
        if self.wrong_aspect_type:
            parts.append(f"{len(self.wrong_aspect_type)} όψεις έχουν λανθασμένο ή απόντα τύπο")
        if self.wrong_weight:
            parts.append(f"{len(self.wrong_weight)} όψεις έχουν λανθασμένη ή απούσα κατηγορία βαρύτητας")
        if self.inconsistent_ruler_box:
            parts.append(f"{len(self.inconsistent_ruler_box)} πλαίσια σύνοψης έχουν κυβερνήτη που δεν συμφωνεί με το κυρίως κείμενο του ίδιου Οίκου")
        if self.wrong_house_claims:
            parts.append(f"{len(self.wrong_house_claims)} λανθασμένες δηλώσεις τοποθέτησης πλανήτη σε Οίκο")
        if self.unauthorized_personal_claims:
            parts.append(f"{len(self.unauthorized_personal_claims)} μη εξουσιοδοτημένες προσωπικές αναφορές")
        return "Η ανάλυση δεν ολοκληρώθηκε: " + "· ".join(parts) + "."

    def details_lines(self) -> list[str]:
        lines = []
        for n in self.missing_houses:
            lines.append(f"Οίκος {n}: δεν βρέθηκε επικεφαλίδα στο κείμενο.")
        for a in self.missing_aspects:
            lines.append(f"{a.first}–{a.second} ({a.aspect}, orb {a.orb_text}): δεν αναφέρεται πουθενά.")
        for a in self.suspect_aspects:
            lines.append(f"{a.first}–{a.second}: αναφέρονται και τα δύο ονόματα, αλλά όχι το orb {a.orb_text} κοντά τους -- έλεγξε χειροκίνητα.")
        for a in self.missing_from_appendix:
            lines.append(f"{a.first}–{a.second}: δεν εντοπίστηκε μέσα στο Παράρτημα Επιβεβαιωμένων Όψεων.")
        for s in self.missing_sections:
            lines.append(f"Λείπει η υποχρεωτική ενότητα: «{s}».")
        for house_n, a in self.missing_per_house:
            lines.append(f"Οίκος {house_n}: η όψη {a.first}–{a.second} (orb {a.orb_text}) δεν αναφέρεται μέσα σε αυτόν τον Οίκο, παρότι εμπλέκει πλανήτη/κυβερνήτη του.")
        for a in self.wrong_aspect_type:
            lines.append(f"{a.first}–{a.second}: αναμενόταν «{a.aspect}» μαζί με orb {a.orb_text}, αλλά ο σωστός τύπος δεν εντοπίστηκε κοντά στο ζεύγος.")
        for a in self.wrong_weight:
            lines.append(f"{a.first}–{a.second}: αναμενόταν βαρύτητα «{a.weight}» μαζί με orb {a.orb_text}, αλλά δεν εντοπίστηκε κοντά στο ζεύγος.")
        for house_n, expected, box_text in self.inconsistent_ruler_box:
            lines.append(f"Οίκος {house_n}: το κυρίως κείμενο ονομάζει κυβερνήτη {', '.join(expected)}, αλλά το πλαίσιο σύνοψης λέει «{box_text}» -- πιθανή αντιγραφή από άλλον Οίκο.")
        for point_name, claimed, expected, snippet in self.wrong_house_claims:
            lines.append(f"Λανθασμένη τοποθέτηση — {point_name}: το κείμενο τον/την δηλώνει στον {claimed}ο Οίκο, ενώ τα ελεγμένα δεδομένα δίνουν {expected}ο Οίκο. Σημείο: {snippet}")
        for category, snippet in self.unauthorized_personal_claims:
            lines.append(f"Μη δηλωμένο προσωπικό στοιχείο ({category}): «{snippet}»")
        return lines


def _find_appendix(text: str) -> str:
    idx = text.find("Παράρτημα")
    return text[idx:] if idx != -1 else ""


def _normalize_prime_marks(text: str) -> str:
    """Κανονικοποιεί το πρόχειρο ' (ASCII apostrophe, U+0027) και το
    τυπογραφικό ' (right single quote, U+2019) σε ′ (πραγματικό σύμβολο
    πρώτου λεπτού τόξου, U+2032) όταν ακολουθεί ψηφίο -- π.χ. "3°30'" ή
    "3°30'" γίνονται "3°30′".

    Γιατί χρειάζεται: κάθε aspect.orb_text (astrology.orb_to_text) και
    κάθε _NAME_FORMS/regex σε αυτό το module χρησιμοποιεί αποκλειστικά το
    ′. Ένα Word που παράγεται από μοντέλο (ή περνάει από αυτόματο smart-
    quote του Word/ChatGPT) μπορεί να γράψει το πρόχειρο απόστροφο αντ'
    αυτού. Χωρίς αυτή την κανονικοποίηση, το ίδιο ακριβώς, σωστό orb
    χαρακτηρίζεται ψευδώς "ύποπτο/απόν" επειδή η αναζήτηση συμβολοσειράς
    (`orb_text in window`, `re.escape(orb_text)` κ.λπ.) απαιτεί ΑΚΡΙΒΩΣ
    το χαρακτήρα ′. Καλείται μία φορά, στην είσοδο κάθε δημόσιας
    validate_*() συνάρτησης -- όλες οι εσωτερικές κλήσεις (per-house
    τμήματα, Παράρτημα κ.λπ.) προέρχονται από ήδη κανονικοποιημένο κείμενο.
    """
    return re.sub(r"(?<=\d)['’]", "′", text)


def _name_pattern(name: str) -> str:
    return _NAME_FORMS.get(name, re.escape(name))


def _co_occurs_with_orb(text: str, name_a: str, name_b: str, orb_text: str,
                        aspect_type: str | None = None,
                        weight: str | None = None) -> tuple[bool, bool, bool, bool]:
    """Επιστρέφει παρουσία ζεύγους, orb, σωστού τύπου και σωστής βαρύτητας."""
    co_occurs = False
    orb_found = False
    type_found = False
    weight_found = False
    pa, pb = _name_pattern(name_a), _name_pattern(name_b)
    for m in re.finditer(pa, text, re.IGNORECASE):
        start = max(0, m.start() - _WINDOW)
        end = min(len(text), m.end() + _WINDOW)
        window = text[start:end]
        if re.search(pb, window, re.IGNORECASE):
            co_occurs = True
            if orb_text in window:
                orb_found = True
                if aspect_type:
                    type_found = bool(re.search(_ASPECT_FORMS.get(aspect_type, re.escape(aspect_type)), window, re.IGNORECASE))
                else:
                    type_found = True
                if weight:
                    weight_found = bool(re.search(_WEIGHT_FORMS.get(weight, re.escape(weight)), window, re.IGNORECASE))
                else:
                    weight_found = True
                if type_found and weight_found:
                    break
    return co_occurs, orb_found, type_found, weight_found


def _contradicts_aspect(text: str, aspect) -> tuple[bool, bool]:
    """Εντοπίζει ρητή λάθος μεταγραφή του τύπου ή της βαρύτητας.

    Εξετάζει κάθε παράγραφο/γραμμή αυτόνομα, ώστε μια σωστή αναφορά σε άλλον
    Οίκο να μην κρύβει ένα λάθος στην τελική σύνθεση. Αν το ζεύγος υπάρχει
    αλλά δεν δηλώνεται καθόλου τύπος ή βαρύτητα, δεν θεωρείται αντίφαση.

    v3: η αναζήτηση τύπου/βαρύτητας αγκυρώνεται πλέον στο πλησιέστερο orb
    ΤΟΥ ΙΔΙΟΥ ζεύγους μέσα στο απόσπασμα -- όχι σε όλο το ευρύ παράθυρο γύρω
    από το ζεύγος. Η παλιά v2 λογική έψαχνε "οποιαδήποτε άλλη κατηγορία/τύπο
    στο παράθυρο" χωρίς να ξέρει σε ποιο ζεύγος ανήκε η λέξη που βρήκε, οπότε
    μια πρόταση όπως «η στενή αντίθεση Α–Β..., ενώ το κανονικό τετράγωνο
    Γ–Δ...» σήκωνε ψευδή αντίφαση για το Α–Β μόνο επειδή το «κανονικό» της
    ΑΛΛΗΣ όψης έπεφτε μέσα στο παράθυρο. Τώρα, αν δεν βρεθεί το ακριβές orb
    του ζεύγους κοντά, δεν βγάζουμε συμπέρασμα (όπως και πριν όταν έλειπε
    τελείως τύπος/βαρύτητα). Επίσης εξαιρούνται οι τύποι που δηλώνουν τη
    συμπληρωματική όψη άξονα («... ως τετράγωνο ...»), με την ίδια λογική
    που ήδη χρησιμοποιεί η _strict_occurrence_errors.
    """
    pa, pb = _name_pattern(aspect.first), _name_pattern(aspect.second)
    wrong_type = False
    wrong_weight = False
    joined = rf"(?:{pa}\s*[–—-]\s*{pb}|{pb}\s*[–—-]\s*{pa})"
    for unit in re.split(r"[\r\n]+", text):
        for pair_match in re.finditer(joined, unit, re.IGNORECASE):
            if _is_chained_false_match(unit, pair_match.start(), pair_match.end(),
                                       pair_match.group(0), pa, pb):
                # Κομμάτι αλυσίδας «Χ–Α–Β»/«Α–Β–Ψ», όχι αυτόνομη αναφορά
                # ζεύγους -- δεν φέρει δικό του τύπο/βαρύτητα όψης.
                continue
            start = max(0, pair_match.start() - 90)
            end = min(len(unit), pair_match.end() + 220)
            fragment = unit[start:end]
            pair_start = pair_match.start() - start
            pair_end = pair_match.end() - start

            orb_matches = list(re.finditer(re.escape(aspect.orb_text), fragment))
            if not orb_matches:
                # Δεν εντοπίστηκε το orb αυτού του ζεύγους κοντά -- δεν
                # μπορούμε να αγκυρώσουμε με σιγουριά ποια λέξη ανήκει σε
                # ποιον, άρα δεν σημαίνουμε αντίφαση από αυτή την εμφάνιση.
                continue
            orb = min(
                orb_matches,
                key=lambda m: min(abs(m.start() - pair_end), abs(m.end() - pair_start)),
            )

            type_labels = [
                item for item in _matched_labels(fragment, _ASPECT_FORMS)
                if not _is_mirrored_axis_type(fragment, item[1])
            ]
            if type_labels:
                nearest_type = min(
                    type_labels,
                    key=lambda item: min(abs(item[1] - pair_end), abs(item[2] - pair_start)),
                )[0]
                if nearest_type != aspect.aspect:
                    wrong_type = True

            after_orb = fragment[orb.end():orb.end() + 95]
            after_labels = _matched_labels(after_orb, _WEIGHT_FORMS)
            if after_labels:
                declared_weight = after_labels[0][0]
            else:
                all_weights = _matched_labels(fragment, _WEIGHT_FORMS)
                declared_weight = min(
                    all_weights,
                    key=lambda item: min(abs(item[1] - orb.end()), abs(item[2] - orb.start())),
                )[0] if all_weights else None
            if declared_weight is not None and declared_weight != aspect.weight:
                wrong_weight = True
    return wrong_type, wrong_weight


def _matched_labels(fragment: str, forms: dict[str, str]) -> list[tuple[str, int, int]]:
    """Επιστρέφει όλους τους αναγνωρισμένους χαρακτηρισμούς και τις θέσεις τους."""
    matches = []
    for label, pattern in forms.items():
        for match in re.finditer(pattern, fragment, re.IGNORECASE):
            matches.append((label, match.start(), match.end()))
    return sorted(matches, key=lambda item: item[1])


_ANY_NAME_ALT = "|".join(_NAME_FORMS.values())
_CONNECTOR_RE = re.compile(r"(?P<sp1>\s*)(?P<dash>[–—-])(?P<sp2>\s*)")
_CHAIN_BEFORE_RE = re.compile(rf"(?:{_ANY_NAME_ALT})(?P<sp1>\s*)(?P<dash>[–—-])(?P<sp2>\s*)$", re.IGNORECASE)
_CHAIN_AFTER_RE = re.compile(rf"^(?P<sp1>\s*)(?P<dash>[–—-])(?P<sp2>\s*)(?:{_ANY_NAME_ALT})", re.IGNORECASE)


def _connector_style(sp1: str, dash: str, sp2: str) -> tuple:
    """Κανονικοποιημένη «υπογραφή» ενός συνδέσμου παύλας: ο χαρακτήρας
    παύλας και αν υπάρχει κενό πριν/μετά. Δύο σύνδεσμοι θεωρούνται «ίδιου
    στιλ» μόνο όταν ταιριάζουν και τα τρία -- π.χ. tight en dash «–» δεν
    ταιριάζει με spaced em dash « — »."""
    return (dash, bool(sp1), bool(sp2))


def _primary_connector_style(matched_text: str, pa: str, pb: str):
    """Στιλ του συνδέσμου ΜΕΣΑ στο ίδιο το ταίριασμα του ζεύγους -- π.χ.
    από «Ουρανός–Πλούτωνας» εξάγει ('–', False, False)."""
    for first, second in ((pa, pb), (pb, pa)):
        m1 = re.match(first, matched_text, re.IGNORECASE)
        if not m1:
            continue
        m2 = re.search(second + r"$", matched_text, re.IGNORECASE)
        if not m2 or m2.start() < m1.end():
            continue
        connector = matched_text[m1.end():m2.start()]
        cm = _CONNECTOR_RE.fullmatch(connector)
        if cm:
            return _connector_style(cm.group("sp1"), cm.group("dash"), cm.group("sp2"))
    return None


def _is_chained_false_match(unit: str, match_start: int, match_end: int,
                            matched_text: str, pa: str, pb: str) -> bool:
    """True όταν ένα ταίριασμα ζεύγους «Α–Β» είναι στην πραγματικότητα
    κομμάτι μιας μεγαλύτερης αλυσίδας ονομάτων «Χ–Α–Β» ή «Α–Β–Ψ»
    (π.χ. «Κρόνος–Ουρανός–Πλούτωνας»), όχι μια αυτόνομη αναφορά ζεύγους.

    Χωρίς αυτόν τον έλεγχο, ο regex pa–pb ταιριάζει και μέσα σε τέτοιες
    φυσικές, τρι-ονοματικές αλυσίδες, και το ψευδές αυτό ταίριασμα μπορεί να
    "κλέψει" τον πλησιέστερο τύπο όψης από μια γειτονική, άσχετη όψη.

    Θεωρείται αλυσίδα ΜΟΝΟ όταν ο διπλανός σύνδεσμος έχει το ΙΔΙΟ στιλ
    παύλας/κενών με τον σύνδεσμο μέσα στο ίδιο το ταίριασμα. Έτσι μια
    πρόταση όπως «Κρόνος–Ουρανός — Πλούτωνας επηρεάζει άλλο θέμα», όπου η
    δεύτερη παύλα είναι διαφορετικού στιλ (πλατιά, με κενά -- πιθανή αρχή
    νέας πρότασης ή παρένθεσης), ΔΕΝ αντιμετωπίζεται ως αλυσίδα ονομάτων."""
    own_style = _primary_connector_style(matched_text, pa, pb)
    if own_style is None:
        return False  # δεν αναγνωρίστηκε ο σύνδεσμος -- δεν αποφασίζουμε
    before = unit[max(0, match_start - 60):match_start]
    after = unit[match_end:match_end + 60]
    mb = _CHAIN_BEFORE_RE.search(before)
    if mb and _connector_style(mb.group("sp1"), mb.group("dash"), mb.group("sp2")) == own_style:
        return True
    ma = _CHAIN_AFTER_RE.match(after)
    if ma and _connector_style(ma.group("sp1"), ma.group("dash"), ma.group("sp2")) == own_style:
        return True
    return False


def _is_mirrored_axis_type(fragment: str, start: int) -> bool:
    """Αληθές όταν ο τύπος όψης δηλώνει τη συμπληρωματική όψη άξονα.

    Παράδειγμα: «Τρίγωνο Σελήνης–Μεσουρανήματος … ενεργοποιεί,
    ως εξάγωνο, τον Πυθμένα Ουρανού». Το «ως εξάγωνο» δεν είναι ο τύπος
    της κύριας όψης και δεν πρέπει να την ακυρώνει στον αυστηρό έλεγχο.
    """
    before = fragment[max(0, start - 18):start]
    return bool(re.search(r"\bως\s*$", before, re.IGNORECASE))


def _strict_occurrence_errors(text: str, aspect) -> tuple[bool, bool]:
    """Δένει αυστηρά ΖΕΥΓΟΣ → ΤΥΠΟ → ORB → ΚΑΤΗΓΟΡΙΑ.

    Ο προηγούμενος έλεγχος αρκούνταν στην παρουσία της σωστής λέξης κάπου
    κοντά στο ζεύγος. Έτσι η φράση «κανονικό τετράγωνο … (orb 3°35′,
    Στενή/ισχυρή)» περνούσε, επειδή έβρισκε το «κανονικό» πριν από το ζεύγος.
    Εδώ, όταν υπάρχει ρητή κατηγορία αμέσως μετά από το συγκεκριμένο orb,
    αυτή έχει προτεραιότητα και πρέπει να συμφωνεί ακριβώς με το registry.
    """
    pa, pb = _name_pattern(aspect.first), _name_pattern(aspect.second)
    joined = rf"(?:{pa}\s*[–—-]\s*{pb}|{pb}\s*[–—-]\s*{pa})"
    wrong_type = False
    wrong_weight = False

    for unit in re.split(r"[\r\n]+", text):
        for pair in re.finditer(joined, unit, re.IGNORECASE):
            if _is_chained_false_match(unit, pair.start(), pair.end(),
                                       pair.group(0), pa, pb):
                continue
            start = max(0, pair.start() - 90)
            end = min(len(unit), pair.end() + 220)
            fragment = unit[start:end]
            pair_start = pair.start() - start
            pair_end = pair.end() - start

            orb_matches = list(re.finditer(re.escape(aspect.orb_text), fragment))
            if not orb_matches:
                continue
            orb = min(
                orb_matches,
                key=lambda match: min(abs(match.start() - pair_end), abs(match.end() - pair_start)),
            )

            # Ο τύπος μπορεί να προηγείται («κανονικό τετράγωνο Α–Β») ή να
            # ακολουθεί σε πίνακα («Α–Β | Τετράγωνο | orb …»). Επιλέγουμε τον
            # πλησιέστερο ρητό τύπο στο ζεύγος.
            type_labels = [
                item for item in _matched_labels(fragment, _ASPECT_FORMS)
                if not _is_mirrored_axis_type(fragment, item[1])
            ]
            if type_labels:
                nearest_type = min(
                    type_labels,
                    key=lambda item: min(abs(item[1] - pair_end), abs(item[2] - pair_start)),
                )[0]
                if nearest_type != aspect.aspect:
                    wrong_type = True

            # Αν υπάρχει κατηγορία μετά από το συγκεκριμένο orb, είναι η
            # κατηγορία που δηλώνεται ρητά για αυτό το orb και υπερισχύει από
            # οποιοδήποτε επίθετο πριν από το ζεύγος.
            after_orb = fragment[orb.end():orb.end() + 95]
            after_labels = _matched_labels(after_orb, _WEIGHT_FORMS)
            if after_labels:
                declared_weight = after_labels[0][0]
            else:
                all_weights = _matched_labels(fragment, _WEIGHT_FORMS)
                declared_weight = min(
                    all_weights,
                    key=lambda item: min(abs(item[1] - orb.end()), abs(item[2] - orb.start())),
                )[0] if all_weights else None
            if declared_weight is not None and declared_weight != aspect.weight:
                wrong_weight = True

    return wrong_type, wrong_weight


def _house_segments(text: str) -> dict[int, str]:
    """Εντοπίζει το τμήμα κειμένου κάθε Οίκου (από την επικεφαλίδα του μέχρι
    την επόμενη), με αναζήτηση με σειρά 1..12 ώστε να μην μπερδεύονται
    αριθμοί Οίκων που αναφέρονται εν παρόδω αλλού στο κείμενο."""
    starts = {}
    cursor = 0
    for n in range(1, 13):
        m = _HOUSE_HEADING_PATTERNS[n - 1].search(text, cursor)
        if not m:
            m = _HOUSE_PATTERNS[n - 1].search(text, cursor) or _HOUSE_PATTERNS_ALT[n - 1].search(text, cursor)
        if not m:
            continue
        starts[n] = m.start()
        cursor = m.start() + 1
    segments = {}
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    for i, (n, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        segments[n] = text[start:end]
    return segments


def _ruler_names_in_body(segment: str) -> list[str]:
    """Εξάγει τα ονόματα πλανητών που το κυρίως κείμενο ενός Οίκου δηλώνει
    ρητά ως κυβερνήτη (σύγχρονο ή/και παραδοσιακό), με τη σειρά εμφάνισης.
    Το ψάξιμο σταματά στο πρώτο κόμμα/τελεία μετά το όνομα, ώστε να μην
    παρασύρει κλιτικές καταλήξεις ή τη συνέχεια της πρότασης."""
    names = []
    for pattern in _RULER_INTRO_PATTERNS:
        for m in pattern.finditer(segment):
            token = m.group(1).rstrip(",.·")
            for canonical, form in _NAME_FORMS.items():
                if re.match(form + r"$", token, re.IGNORECASE):
                    if canonical not in names:
                        names.append(canonical)
                    break
    return names


def _box_ruler_text(segment: str) -> str | None:
    """Επιστρέφει το περιεχόμενο της γραμμής «Κυβερνήτης: ...» μέσα στο
    πλαίσιο σύνοψης ενός Οίκου, ή None αν δεν βρέθηκε καθόλου."""
    m = _BOX_RULER_LINE.search(segment)
    return m.group(1).strip() if m else None


def _involved_points(chart, house_number: int) -> set[str]:
    """Ίδια λογική με prompts.house_section: πλανήτες μέσα στον Οίκο, κύριος
    και παραδοσιακός κυβερνήτης, και -- για τους Οίκους 1/7/4/10 -- η γωνία
    που ο ίδιος ο Οίκος ορίζει (κανόνας 6Β)."""
    cusp = chart.cusps[house_number - 1]
    planets = [p for p in chart.points if p.house == house_number and p.kind in ("planet", "node")]
    modern_ruler, traditional_ruler = RULERS[cusp.sign]
    involved = {p.name for p in planets}
    involved.add(modern_ruler)
    if traditional_ruler:
        involved.add(traditional_ruler)
    if house_number in (1, 7):
        involved.add("Ωροσκόπος")
    if house_number in (4, 10):
        involved.add("Μεσουράνημα")
    return involved


def _claim_belongs_to_other_point(snippet: str, point_name: str) -> bool:
    """True όταν η δήλωση τοποθέτησης στο απόσπασμα αφορά ΑΛΛΟ σημείο.

    Το regex του _location_claim_errors επιτρέπει έως 90 χαρακτήρες ανάμεσα
    στο όνομα και στο ρήμα. Έτσι, σε πρόταση όπως
    «Ο Βόρειος Δεσμός στον Καρκίνο κυβερνάται από τη Σελήνη, η οποία
    βρίσκεται … στον 10ο Οίκο», ο 10ος Οίκος αποδιδόταν λανθασμένα στον
    Βόρειο Δεσμό. Το υποκείμενο του «βρίσκεται» είναι το πλησιέστερο
    προηγούμενο σημείο, όχι το πρώτο της πρότασης.

    Επιστρέφει True αν, μετά το αρχικό όνομα, εμφανίζεται άλλο σημείο του
    χάρτη πριν από τον αριθμό του Οίκου. Το άλλο σημείο ελέγχεται κανονικά
    με τη δική του αντιστοίχιση, οπότε μια πραγματικά λάθος δήλωση δεν
    χάνεται.
    """
    own = re.match(_name_pattern(point_name), snippet, re.IGNORECASE)
    rest = snippet[own.end():] if own else snippet
    for other, pattern in _NAME_FORMS.items():
        if other == point_name:
            continue
        # «Βόρειος Δεσμός» περιέχει «Δεσμός» -- τα ονόματα δεν επικαλύπτονται
        # με τα υπόλοιπα, οπότε αρκεί απλή αναζήτηση.
        if re.search(pattern, rest, re.IGNORECASE):
            return True
    return False


def _claim_context(text: str, start: int, end: int, segments_bounds) -> str:
    """Επιστρέφει «ενότητα · «ολόκληρη πρόταση»» για μια δήλωση τοποθέτησης,
    ώστε το μήνυμα λάθους να δείχνει ακριβώς πού βρίσκεται το πρόβλημα."""
    left = max(text.rfind(ch, 0, start) for ch in ".!?\n")
    right_candidates = [i for i in (text.find(ch, end) for ch in ".!?\n") if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    sentence = " ".join(text[left + 1:right].split())
    section = "εκτός των ενοτήτων των Οίκων"
    for n, s0, e0 in segments_bounds:
        if s0 <= start < e0:
            section = f"ενότητα {n}ου Οίκου"
            break
    return f"{section} · πρόταση: «{sentence}»"


def _segments_bounds(text: str):
    """(Οίκος, αρχή, τέλος) κάθε ενότητας Οίκου. Ο 12ος τελειώνει πριν από
    τις τελικές ενότητες, αν αυτές εντοπίζονται."""
    starts = []
    cursor = 0
    for n in range(1, 13):
        m = _HOUSE_HEADING_PATTERNS[n - 1].search(text, cursor)
        if not m:
            m = _HOUSE_PATTERNS[n - 1].search(text, cursor) or _HOUSE_PATTERNS_ALT[n - 1].search(text, cursor)
        if m:
            starts.append((n, m.start()))
            cursor = m.start() + 1
    final_idx = text.find("Τελική συνθετική εικόνα", starts[-1][1] if starts else 0)
    tail_end = final_idx if final_idx != -1 else len(text)
    bounds = []
    for i, (n, st) in enumerate(starts):
        en = starts[i + 1][1] if i + 1 < len(starts) else tail_end
        bounds.append((n, st, en))
    return bounds


def _location_claim_errors(chart, text: str) -> list[tuple[str, int, int, str]]:
    """Detect only affirmative location statements, avoiding thematic links.

    The check intentionally targets phrases such as "ο Άρης βρίσκεται στον 7ο"
    or "ο Άρης βρίσκεται στο πεδίο των σχέσεων".  It does not reject a valid
    sentence saying that a planet in one house *connects* with another field.
    """
    theme_houses = {
        1: r"ταυτότητ|προσωπικ(?:ή|ης)\s+παρουσ",
        2: r"προσωπικ(?:ή|ης)\s+αξί|πόρ(?:ων|ους)",
        3: r"επικοινωνί|μάθησ",
        4: r"οικογένει|ριζ(?:ών|ες)|σπιτ",
        5: r"δημιουργικότητ|παιδι(?:ών|ά)|χαρά",
        6: r"καθημεριν(?:ή|ης)\s+εργασ|ρουτίν|υγεί",
        7: r"σχέσε(?:ων|ών|ις)|γάμ(?:ου|ος)|συνεργασ",
        8: r"κοιν(?:ών|ά)\s+οικονομ|εμπιστοσύν|μεταμόρφωσ",
        9: r"νοήματ|ανώτερ(?:η|ης)\s+παιδε|φιλοσοφ",
        10: r"καριέρα|δημόσια(?:ς|\s+)\s*(?:σου\s+)?πορεία|επαγγελματικ(?:ή|ης)\s+πορεία",
        11: r"οραμάτων|κοινότητ|ομάδ|φίλ",
        12: r"εσωτερικ(?:ό|ού)\s+κόσμ|παρασκήν|ασυνείδητ",
    }
    errors = []
    bounds = _segments_bounds(text)
    for point in chart.points:
        if point.house is None or point.kind not in ("planet", "node"):
            continue
        name = _name_pattern(point.name)
        # Explicit numeric placement.
        numeric = re.compile(
            rf"{name}[^.!?\n]{{0,90}}?(?:βρίσκεται|είναι|τοποθετείται|κατοικεί|Θέση\s*:)[^.!?\n]{{0,45}}?(\d{{1,2}})\s*(?:ος|ο|ου)?\s*Οίκ",
            re.IGNORECASE,
        )
        # Symbolic house label used as if it were a physical placement.
        thematic = re.compile(
            rf"{name}[^.!?\n]{{0,70}}?(?:βρίσκεται|είναι|τοποθετείται|κατοικεί)\s+(?:μέσα\s+)?στο\s+πεδίο\s+(?:της|των)\s+([^—.!?\n]{{2,55}})",
            re.IGNORECASE,
        )
        for match in numeric.finditer(text):
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            claimed = int(match.group(1))
            if 1 <= claimed <= 12 and claimed != point.house:
                errors.append((point.name, claimed, point.house,
                               _claim_context(text, match.start(), match.end(), bounds)))
        for match in thematic.finditer(text):
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            label = match.group(1)
            claimed = next((n for n, pat in theme_houses.items() if re.search(pat, label, re.IGNORECASE)), None)
            if claimed and claimed != point.house:
                errors.append((point.name, claimed, point.house,
                               _claim_context(text, match.start(), match.end(), bounds)))
    return errors


def _unauthorized_personal_claims(personal: dict | None, text: str) -> list[tuple[str, str]]:
    """Εντοπίζει επινοημένα προσωπικά στοιχεία που ΔΕΝ δηλώθηκαν στο
    ΠΡΟΣΩΠΙΚΟ ΠΛΑΙΣΙΟ.

    ΠΡΟΣΟΧΗ -- γνωστός περιορισμός: αυτή η λίστα είναι αναγκαστικά μια
    allowlist συγκεκριμένων φράσεων, όχι γενικός σημασιολογικός έλεγχος.
    Καλύπτει τις κατηγορίες που αντιστοιχούν σε πεδία του ΠΡΟΣΩΠΙΚΟΥ
    ΠΛΑΙΣΙΟΥ (tab3 του app.py), αλλά μια αρκετά διαφορετική διατύπωση από
    αυτή που ήδη περιμένουν τα regex θα περάσει απαρατήρητη. Δεν
    αντικαθιστά την ανθρώπινη ανάγνωση της τελικής ανάλυσης.
    """
    personal = personal or {}
    checks = []
    if not (personal.get("Επάγγελμα και σπουδές") or "").strip():
        checks.append(("επάγγελμα/σπουδές", r"[^.!?\n]{0,45}(?:καθηγήτρια|καθηγητής|διδασκαλία\s+(?:της\s+)?φυσικής|στο\s+επάγγελμά\s+σου|εργάζεσαι\s+σε\s+σχολ|έχεις\s+μεταπτυχιακό|το\s+πτυχίο\s+σου)[^.!?\n]{0,70}"))
    if not (personal.get("Οικογενειακή κατάσταση") or "").strip():
        checks.append(("οικογενειακή κατάσταση", r"[^.!?\n]{0,45}(?:με\s+(?:τα\s+)?δύο\s+(?:σου\s+)?παιδιά|έχεις\s+δύο\s+παιδιά|ως\s+μητέρα|ως\s+πατέρας|ο\s+σύζυγός\s+σου|η\s+σύζυγός\s+σου)[^.!?\n]{0,70}"))
    if not (personal.get("Εργασιακές συνήθειες") or "").strip():
        checks.append(("εργασιακές συνήθειες", r"[^.!?\n]{0,45}(?:επαγγελματική\s+κόπωση|επαγγελματική\s+εξουθένωση|burnout)[^.!?\n]{0,70}"))
    if not (personal.get("Έργα/ενδιαφέροντα") or "").strip():
        checks.append(("έργα/στόχοι", r"[^.!?\n]{0,45}(?:θέλεις\s+να\s+αλλάξεις\s+καριέρα|το\s+έργο\s+σου\s+(?:στο|στην|με))[^.!?\n]{0,70}"))
    found = []
    for category, pattern in checks:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            found.append((category, match.group(0).strip()))
    return found


# ---------------------------------------------------------------------------
# Κοινές βοηθητικές συναρτήσεις για validate_analysis() και validate_rewrite()
# ---------------------------------------------------------------------------
# Εξήχθησαν ώστε ο ορισμός "ποιες όψεις είναι υποχρεωτικές" και η λογική
# "έλεγξε αν αυτή η λίστα όψεων εμφανίζεται σωστά σε αυτό το κείμενο" να
# υπάρχουν σε ΕΝΑ σημείο. Πριν, ο validate_rewrite() είχε είτε καθόλου
# αντίστοιχο έλεγχο είτε (σε ενδιάμεση διόρθωση) δική του, ξεχωριστή
# αντιγραφή της ίδιας λογικής -- κίνδυνος να αποκλίνουν ξανά σε μελλοντική
# αλλαγή κανόνα (π.χ. αν προστεθεί νέα κατηγορία υποχρεωτικής όψης).

def _mandatory_aspects(chart):
    """Τετράγωνα, αντιθέσεις, και σύνοδοι με γωνία (Ωροσκόπος/Μεσουράνημα).

    Αυτές είναι υποχρεωτικές στη βασική ανάλυση (validate_analysis) ΚΑΙ
    δεν επιτρέπεται να εξαφανιστούν σε καμία μεταγενέστερη αναδιατύπωση
    (validate_rewrite) -- ανεξάρτητα από το ότι επιτρέπεται λιγότερη
    τεχνική ορολογία στο σώμα κειμένου.
    """
    hard = [a for a in chart.aspects if a.aspect in ("Τετράγωνο", "Αντίθεση")]
    angle_conjunctions = [
        a for a in chart.aspects
        if a.aspect == "Σύνοδος" and (a.first in ANGLE_NAMES or a.second in ANGLE_NAMES)
    ]
    return hard + angle_conjunctions


def _check_aspects_present(text: str, aspects: list):
    """Για κάθε όψη της λίστας: co_occurs/orb_ok/type_ok/weight_ok μέσω
    _co_occurs_with_orb(). Επιστρέφει (missing, suspect, wrong_type,
    wrong_weight). ΔΕΝ απαιτεί κάθε όψη να εμφανίζεται σε ΚΑΘΕ τμήμα του
    κειμένου -- ελέγχει μόνο αν εμφανίζεται σωστά ΚΑΠΟΥ μέσα στο `text`
    που της δόθηκε (π.χ. ολόκληρο το κείμενο, ή μόνο το Παράρτημα, ή μόνο
    ένας Οίκος -- αποφασίζει ο καλών).
    """
    missing, suspect, wrong_type, wrong_weight = [], [], [], []
    for a in aspects:
        co_occurs, orb_ok, type_ok, weight_ok = _co_occurs_with_orb(
            text, a.first, a.second, a.orb_text, a.aspect, a.weight
        )
        if not co_occurs:
            missing.append(a)
        elif not orb_ok:
            suspect.append(a)
        else:
            if not type_ok:
                wrong_type.append(a)
            if not weight_ok:
                wrong_weight.append(a)
    return missing, suspect, wrong_type, wrong_weight


def _dedupe_aspects(*lists) -> list:
    """Ένωση λιστών από Aspect χωρίς διπλότυπα, με τη σειρά εμφάνισης.

    Το Aspect (models.py) είναι απλό @dataclass χωρίς frozen=True, άρα
    ΔΕΝ είναι hashable (η Python μηδενίζει το __hash__ όταν ορίζεται
    __eq__ χωρίς frozen). dict.fromkeys()/set() θα έσκαγαν με
    TypeError: unhashable type. Εδώ γίνεται dedup με ισότητα (__eq__),
    το οποίο ήδη λειτουργεί σωστά για το Aspect.
    """
    result = []
    for lst in lists:
        for item in lst:
            if item not in result:
                result.append(item)
    return result


def validate_analysis(chart, analysis_text: str, personal: dict | None = None) -> ValidationResult:
    text = _normalize_prime_marks(analysis_text)

    missing_houses = []
    for n in range(1, 13):
        if _HOUSE_PATTERNS[n - 1].search(text) or _HOUSE_PATTERNS_ALT[n - 1].search(text):
            continue
        missing_houses.append(n)

    # v2: mandatory = τετράγωνα/αντιθέσεις (όπως πριν) ΣΥΝ κάθε σύνοδο όπου
    # συμμετέχει γωνία (Ωροσκόπος/Μεσουράνημα) -- πριν αγνοούνταν εντελώς.
    mandatory = _mandatory_aspects(chart)
    missing_aspects, suspect_aspects, wrong_aspect_type, wrong_weight = \
        _check_aspects_present(text, mandatory)

    appendix_text = _find_appendix(text)
    missing_from_appendix = []
    if appendix_text:
        # ίδια βοηθητική με το validate_rewrite() (βλ. _check_aspects_present) --
        # εδώ διατηρείται σκόπιμα σαν ενιαία λίστα αποτυχίας (ανεξαρτήτως
        # missing/suspect/wrong_type/wrong_weight), όπως ήταν πάντα το πεδίο
        # missing_from_appendix του ValidationResult.
        m, s, wt, ww = _check_aspects_present(appendix_text, chart.aspects)
        missing_from_appendix = _dedupe_aspects(m, s, wt, ww)

    missing_sections = [
        section for section in REQUIRED_SECTIONS
        if not re.search(_SECTION_PATTERNS[section], text, re.IGNORECASE)
    ]

    # v2: έλεγχος ανά Οίκο (κανόνας 6Β) -- κάθε mandatory όψη πρέπει να
    # εμφανίζεται ΜΕΣΑ στο τμήμα κειμένου κάθε Οίκου όπου εμπλέκεται
    # πλανήτης/κυβερνήτης/γωνία του, όχι απλώς κάπου στο έγγραφο.
    missing_per_house = []
    segments = _house_segments(text)
    for house_number in range(1, 13):
        segment = segments.get(house_number)
        if not segment:
            continue  # ήδη καταγράφηκε στο missing_houses
        involved = _involved_points(chart, house_number)
        for a in mandatory:
            if a.first not in involved and a.second not in involved:
                continue
            co_occurs, orb_ok, type_ok, weight_ok = _co_occurs_with_orb(
                segment, a.first, a.second, a.orb_text, a.aspect, a.weight
            )
            if not (co_occurs and orb_ok):
                missing_per_house.append((house_number, a))

    # v3: κάθε Οίκος πρέπει να δηλώνει τον ίδιο κυβερνήτη και στο κυρίως
    # κείμενο και στο πλαίσιο σύνοψής του -- βλ. σημείωση v3 στην κορυφή
    # του module.
    inconsistent_ruler_box = []
    for house_number in range(1, 13):
        segment = segments.get(house_number)
        if not segment:
            continue  # ήδη καταγράφηκε στο missing_houses
        expected = _ruler_names_in_body(segment)
        if not expected:
            continue  # δεν εντοπίστηκε δηλωμένος κυβερνήτης στο κείμενο -- τίποτα να συγκρίνουμε
        box_text = _box_ruler_text(segment)
        if box_text is None:
            continue  # δεν υπάρχει καθόλου πλαίσιο σύνοψης -- άλλο θέμα, όχι ασυνέπεια
        if not all(re.search(_name_pattern(name), box_text, re.IGNORECASE) for name in expected):
            inconsistent_ruler_box.append((house_number, expected, box_text))

    wrong_house_claims = _location_claim_errors(chart, text)
    unauthorized_personal_claims = _unauthorized_personal_claims(personal, text)

    # Έλεγχος συνέπειας ΟΛΩΝ των αναφερόμενων όψεων, όχι μόνο των
    # υποχρεωτικών τετραγώνων/αντιθέσεων. Έτσι εντοπίζεται, για παράδειγμα,
    # λάθος κατηγορία σε σύνοδο Ήλιου–Άρη ή λάθος τύπος σε τελική σύνθεση.
    for a in chart.aspects:
        bad_type, bad_weight = _contradicts_aspect(text, a)
        strict_bad_type, strict_bad_weight = _strict_occurrence_errors(text, a)
        bad_type = bad_type or strict_bad_type
        bad_weight = bad_weight or strict_bad_weight
        if bad_type and a not in wrong_aspect_type:
            wrong_aspect_type.append(a)
        if bad_weight and a not in wrong_weight:
            wrong_weight.append(a)

    ok = not (missing_houses or missing_aspects or suspect_aspects
              or missing_from_appendix or missing_sections or missing_per_house
              or wrong_aspect_type or wrong_weight or inconsistent_ruler_box
              or wrong_house_claims or unauthorized_personal_claims)
    return ValidationResult(ok, missing_houses, missing_aspects, suspect_aspects,
                             missing_from_appendix, missing_sections, missing_per_house,
                             wrong_aspect_type, wrong_weight, inconsistent_ruler_box,
                             wrong_house_claims, unauthorized_personal_claims)


# Η τελική αναδιατύπωση είναι το έντυπο που βλέπει ο πελάτης. ΔΕΝ πρέπει να
# περιέχει τεχνικά αστρολογικά δεδομένα: μοίρες, orb, κατηγορίες βαρύτητας,
# πίνακα/Παράρτημα όψεων ή ενδείξεις πηγής. Τα τεχνικά στοιχεία μένουν στο
# ελεγμένο τεχνικό Word (validate_analysis), που τα περιέχει αυτούσια.
_CLOSING_SENTENCE = ("Αυτή η ανάλυση βασίζεται σε πλήρη μαθηματικό έλεγχο όλων των "
                     "αστρολογικών όψεων του χάρτη σου· τα τεχνικά στοιχεία είναι "
                     "διαθέσιμα αν θες να τα δεις.")

_CLIENT_TECHNICAL_PATTERNS = [
    ("μοίρες/λεπτά", re.compile(r"\d{1,3}\s*°(?:\s*\d{1,2}\s*′)?(?:\s*\d{1,2}\s*″)?")),
    ("orb", re.compile(r"(?<![A-Za-z])orb(?![A-Za-z])", re.IGNORECASE)),
    ("κατηγορία βαρύτητας", re.compile(
        r"Στενή\s*/\s*ισχυρή|Πλατιά\s+αλλά\s+έγκυρη|Πολύ\s+πλατιά\s*/\s*δευτερεύουσα",
        re.IGNORECASE)),
    ("Παράρτημα/πίνακας όψεων", re.compile(
        r"(?m)^\s*(?:Τεχνικό\s+)?Παράρτημα\b|Παράρτημα[^\r\n]{0,90}επιβεβαιωμέν\w*[^\r\n]{0,40}όψε(?:ων|ις)",
        re.IGNORECASE)),
    ("ένδειξη τεχνικής πηγής", re.compile(
        r"Πίνακας\s+Astrodienst|Μαθηματική\s+παραγωγή\s+από\s+τον\s+άξονα", re.IGNORECASE)),
]


def _client_technical_data(text: str) -> list[tuple[str, str]]:
    """(κατηγορία, πρόταση) για κάθε σημείο όπου εμφανίζεται τεχνικό δεδομένο.
    Μία εγγραφή ανά πρόταση και κατηγορία, ώστε ο πίνακας όψεων να μη βγάζει
    εκατοντάδες γραμμές για το ίδιο πρόβλημα."""
    found, seen = [], set()
    for category, pattern in _CLIENT_TECHNICAL_PATTERNS:
        for m in pattern.finditer(text):
            left = max(text.rfind(ch, 0, m.start()) for ch in ".!?\n")
            rights = [i for i in (text.find(ch, m.end()) for ch in ".!?\n") if i != -1]
            right = min(rights) + 1 if rights else len(text)
            sentence = " ".join(text[left + 1:right].split())[:220]
            key = (category, sentence)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found


def _has_closing_sentence(text: str) -> bool:
    norm = " ".join(text.split())
    return norm.rstrip().endswith(" ".join(_CLOSING_SENTENCE.split()))


@dataclass
class RewriteValidationResult:
    ok: bool
    missing_houses: list = field(default_factory=list)
    missing_source_sections: list = field(default_factory=list)
    invented_sections: list = field(default_factory=list)
    wrong_house_claims: list = field(default_factory=list)
    unauthorized_personal_claims: list = field(default_factory=list)
    # (κατηγορία, πρόταση): τεχνικά αστρολογικά δεδομένα που ο πελάτης δεν
    # πρέπει να βλέπει (μοίρες, orb, βαρύτητες, Παράρτημα, πηγή).
    technical_data: list = field(default_factory=list)
    missing_closing_sentence: bool = False

    def summary(self) -> str:
        if self.ok:
            return ("✓ Η τελική αναδιατύπωση πέρασε τον έλεγχο: 12 Οίκοι, όλες οι ενότητες της πηγής, "
                    "σωστές τοποθετήσεις, χωρίς τεχνικά αστρολογικά δεδομένα (μοίρες, orb, βαρύτητες, "
                    "Παράρτημα) και με την υποχρεωτική τελική πρόταση.")
        counts = []
        if self.missing_houses: counts.append(f"λείπουν Οίκοι: {', '.join(map(str, self.missing_houses))}")
        if self.missing_source_sections: counts.append("λείπουν υποχρεωτικές ενότητες της πηγής: " + ", ".join(self.missing_source_sections))
        if self.invented_sections: counts.append("προστέθηκαν ενότητες που δεν υπήρχαν στην πηγή: " + ", ".join(self.invented_sections))
        if self.wrong_house_claims: counts.append(f"{len(self.wrong_house_claims)} λανθασμένες τοποθετήσεις")
        if self.unauthorized_personal_claims: counts.append(f"{len(self.unauthorized_personal_claims)} μη εξουσιοδοτημένες προσωπικές αναφορές")
        if self.technical_data: counts.append(f"{len(self.technical_data)} σημεία με τεχνικά αστρολογικά δεδομένα που δεν πρέπει να βλέπει ο πελάτης")
        if self.missing_closing_sentence: counts.append("λείπει ή έχει αλλοιωθεί η υποχρεωτική τελική πρόταση")
        return "Η αναδιατύπωση απορρίφθηκε: " + "· ".join(counts) + "."

    def details_lines(self) -> list[str]:
        lines = []
        for n in self.missing_houses: lines.append(f"Δεν εντοπίστηκε ο {n}ος Οίκος.")
        for s in self.missing_source_sections: lines.append(f"Η πηγή περιέχει την ενότητα «{s}», αλλά η αναδιατύπωση την παρέλειψε.")
        for s in self.invented_sections: lines.append(f"Η αναδιατύπωση πρόσθεσε την ενότητα «{s}», παρότι δεν υπάρχει στην ελεγμένη πηγή.")
        for point_name, claimed, expected, snippet in self.wrong_house_claims:
            lines.append(f"Λανθασμένη τοποθέτηση — {point_name}: δηλώνεται στον {claimed}ο αντί στον {expected}ο Οίκο. Σημείο: {snippet}")
        for category, snippet in self.unauthorized_personal_claims:
            lines.append(f"Μη δηλωμένο προσωπικό στοιχείο ({category}): «{snippet}»")
        shown = self.technical_data[:40]
        for category, sentence in shown:
            lines.append(f"Τεχνικό δεδομένο ({category}) — να αφαιρεθεί από το έντυπο του πελάτη: «{sentence}»")
        if len(self.technical_data) > len(shown):
            lines.append(f"…και {len(self.technical_data) - len(shown)} ακόμη σημεία με τεχνικά δεδομένα "
                         "(συνήθως γραμμές πίνακα/Παραρτήματος όψεων).")
        if self.missing_closing_sentence:
            lines.append("Η τελευταία πρόταση του εγγράφου πρέπει να είναι αυτούσια: «" + _CLOSING_SENTENCE + "»")
        return lines


def validate_rewrite(chart, source_text: str, rewrite_text: str,
                     personal: dict | None = None) -> RewriteValidationResult:
    """Έλεγχος του τελικού εντύπου πελάτη.

    Η πηγή (ελεγμένο τεχνικό Word) περιέχει τα τεχνικά δεδομένα και το
    Παράρτημα· η αναδιατύπωση ΔΕΝ πρέπει να τα περιέχει. Ελέγχεται ότι:
    υπάρχουν οι 12 Οίκοι και οι ερμηνευτικές ενότητες της πηγής, δεν
    προστέθηκαν νέες ενότητες, δεν υπάρχουν λάθος τοποθετήσεις πλανητών ή
    μη δηλωμένα προσωπικά στοιχεία, δεν εμφανίζονται μοίρες/orb/βαρύτητες/
    Παράρτημα και το έγγραφο κλείνει με την υποχρεωτική πρόταση.
    """
    source_text = _normalize_prime_marks(source_text)
    rewrite_text = _normalize_prime_marks(rewrite_text)
    missing_houses = [n for n in range(1, 13)
                      if not (_HOUSE_PATTERNS[n - 1].search(rewrite_text)
                              or _HOUSE_PATTERNS_ALT[n - 1].search(rewrite_text))]
    # Το Παράρτημα δεν μεταφέρεται στο έντυπο πελάτη -- ελέγχεται ξεχωριστά
    # ως τεχνικό δεδομένο, όχι ως ενότητα που «λείπει».
    tracked_sections = [s for s in _SECTION_PATTERNS if not s.startswith("Παράρτημα")]
    source_has = {s: bool(re.search(_SECTION_PATTERNS[s], source_text, re.IGNORECASE)) for s in tracked_sections}
    rewrite_has = {s: bool(re.search(_SECTION_PATTERNS[s], rewrite_text, re.IGNORECASE)) for s in tracked_sections}
    missing_source_sections = [s for s in tracked_sections if source_has[s] and not rewrite_has[s]]
    invented_sections = [s for s in tracked_sections if not source_has[s] and rewrite_has[s]]
    wrong_house_claims = _location_claim_errors(chart, rewrite_text)
    unauthorized = _unauthorized_personal_claims(personal, rewrite_text)
    technical = _client_technical_data(rewrite_text)
    missing_closing = not _has_closing_sentence(rewrite_text)

    ok = not (missing_houses or missing_source_sections or invented_sections
              or wrong_house_claims or unauthorized or technical or missing_closing)
    return RewriteValidationResult(
        ok, missing_houses, missing_source_sections, invented_sections,
        wrong_house_claims, unauthorized, technical, missing_closing,
    )


