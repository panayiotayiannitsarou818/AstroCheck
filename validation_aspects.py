"""Έλεγχος όψεων μέσα στο κείμενο: αν κάθε υποχρεωτική όψη αναφέρεται με σωστό τύπο, orb και κατηγορία βαρύτητας.

Μέρος του validator (βλ. validator.py για το ιστορικό και τη συνολική περιγραφή)."""

from __future__ import annotations
import re

from validation_patterns import (
    ANGLE_NAMES,
    _ASPECT_FORMS,
    _NAME_FORMS,
    _WEIGHT_FORMS,
    _WINDOW,
    _name_pattern,
)


def _co_occurs_with_orb(
    text: str,
    name_a: str,
    name_b: str,
    orb_text: str,
    aspect_type: str | None = None,
    weight: str | None = None,
) -> tuple[bool, bool, bool, bool]:
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
                    type_found = bool(
                        re.search(
                            _ASPECT_FORMS.get(aspect_type, re.escape(aspect_type)),
                            window,
                            re.IGNORECASE,
                        )
                    )
                else:
                    type_found = True
                if weight:
                    weight_found = bool(
                        re.search(
                            _WEIGHT_FORMS.get(weight, re.escape(weight)), window, re.IGNORECASE
                        )
                    )
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
            if _is_chained_false_match(
                unit, pair_match.start(), pair_match.end(), pair_match.group(0), pa, pb
            ):
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
                item
                for item in _matched_labels(fragment, _ASPECT_FORMS)
                if not _is_mirrored_axis_type(fragment, item[1])
            ]
            if type_labels:
                nearest_type = min(
                    type_labels,
                    key=lambda item: min(abs(item[1] - pair_end), abs(item[2] - pair_start)),
                )[0]
                if nearest_type != aspect.aspect:
                    wrong_type = True

            after_orb = fragment[orb.end() : orb.end() + 95]
            after_labels = _matched_labels(after_orb, _WEIGHT_FORMS)
            if after_labels:
                declared_weight = after_labels[0][0]
            else:
                all_weights = _matched_labels(fragment, _WEIGHT_FORMS)
                declared_weight = (
                    min(
                        all_weights,
                        key=lambda item: min(abs(item[1] - orb.end()), abs(item[2] - orb.start())),
                    )[0]
                    if all_weights
                    else None
                )
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


_CHAIN_BEFORE_RE = re.compile(
    rf"(?:{_ANY_NAME_ALT})(?P<sp1>\s*)(?P<dash>[–—-])(?P<sp2>\s*)$", re.IGNORECASE
)


_CHAIN_AFTER_RE = re.compile(
    rf"^(?P<sp1>\s*)(?P<dash>[–—-])(?P<sp2>\s*)(?:{_ANY_NAME_ALT})", re.IGNORECASE
)


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
        connector = matched_text[m1.end() : m2.start()]
        cm = _CONNECTOR_RE.fullmatch(connector)
        if cm:
            return _connector_style(cm.group("sp1"), cm.group("dash"), cm.group("sp2"))
    return None


def _is_chained_false_match(
    unit: str, match_start: int, match_end: int, matched_text: str, pa: str, pb: str
) -> bool:
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
    before = unit[max(0, match_start - 60) : match_start]
    after = unit[match_end : match_end + 60]
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
    before = fragment[max(0, start - 18) : start]
    return bool(re.search(r"\b(?:ως|as(?:\s+an?)?)\s*$", before, re.IGNORECASE))


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
            if _is_chained_false_match(unit, pair.start(), pair.end(), pair.group(0), pa, pb):
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
                item
                for item in _matched_labels(fragment, _ASPECT_FORMS)
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
            after_orb = fragment[orb.end() : orb.end() + 95]
            after_labels = _matched_labels(after_orb, _WEIGHT_FORMS)
            if after_labels:
                declared_weight = after_labels[0][0]
            else:
                all_weights = _matched_labels(fragment, _WEIGHT_FORMS)
                declared_weight = (
                    min(
                        all_weights,
                        key=lambda item: min(abs(item[1] - orb.end()), abs(item[2] - orb.start())),
                    )[0]
                    if all_weights
                    else None
                )
            if declared_weight is not None and declared_weight != aspect.weight:
                wrong_weight = True

    return wrong_type, wrong_weight


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
        a
        for a in chart.aspects
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
