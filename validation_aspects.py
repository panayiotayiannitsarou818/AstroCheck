"""Έλεγχος όψεων μέσα στο κείμενο: αν κάθε υποχρεωτική όψη αναφέρεται με σωστό τύπο, orb και κατηγορία βαρύτητας.

Μέρος του validator (βλ. validator.py για το ιστορικό και τη συνολική περιγραφή)."""

from __future__ import annotations
import re

from validation_patterns import (
    ANGLE_NAMES,
    _normalize_prime_marks,
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
        if a.aspect == "Σύνοδος"
        and (a.first in ANGLE_NAMES or a.second in ANGLE_NAMES)
        # Ανεξαρτήτως πηγής (πίνακας Astrodienst ή υπολογισμός από τις θέσεις):
        # η προέλευση μιας συνόδου με γωνία δεν αλλάζει την υποχρέωση (κανόνας 6Β).
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


# ---------------------------------------------------------------------------
# v4/v5: όψεις που το κείμενο ΔΗΛΩΝΕΙ αλλά δεν υπάρχουν στον ελεγμένο χάρτη.
# Όλοι οι παραπάνω έλεγχοι ξεκινούν από το chart.aspects, άρα ένα επινοημένο
# ζεύγος δεν ελεγχόταν ποτέ. Εξετάζονται διαδοχικά ονόματα στην ίδια πρόταση
# και αναγνωρίζονται ΜΟΝΟ γραμματικά ρητές δηλώσεις όψης:
#   Α. «Ήλιος–Σελήνη τετράγωνο …»                    (ζεύγος με παύλα, τύπος μετά)
#   Β. «τετράγωνο Ήλιου–Σελήνης», «το τετράγωνο του Ήλιου με τη Σελήνη»,
#      «square between the Sun and the Moon»           (τύπος πριν από το ζεύγος)
#   Γ. «Ο Ήλιος (σχηματίζει) τετράγωνο με τη Σελήνη», «Ήλιος τετράγωνο Σελήνη»,
#      «The Sun forms a square with the Moon», «Sun square Moon»
# Κάθε τέτοια δήλωση είναι σφάλμα, με ή χωρίς orb. Αρνήσεις («δεν σχηματίζει»)
# και προτάσεις όπου το υποκείμενο είναι αμφίσημο («… και τρίγωνο με τη Χ»)
# αγνοούνται σκόπιμα -- προτιμάται να χαθεί μια αμφίσημη περίπτωση παρά να
# μπλοκαριστεί σωστή ανάλυση.
# ---------------------------------------------------------------------------
_ANY_ASPECT = "(?:" + "|".join(_ASPECT_FORMS.values()) + ")"
_ART = r"(?:(?:ο|η|τον|την|τη|το|του|της|the)\s+)?"
_DASH = r"\s*[–—-]\s*"
_LINK = rf"(?:{_DASH}|\s+(?:με|και|and|with|to|προς)\s+{_ART})"
# Γ: ό,τι μπαίνει ανάμεσα στο υποκείμενο και τον τύπο (μόνο ρήμα/άρθρο).
_VERB = (
    r"(?:(?:σχηματίζ\w*|κάνει|κάνουν|δημιουργ\w*|έχει|έχουν|βρίσκ\w+|είναι|"
    r"forms?|makes?|has|have|is|are)\s+)?"
    r"(?:(?:ένα|ενός|μια|μία|σε|a|an|in)\s+){0,2}"
    # v8: συνήθη επίθετα/επιρρήματα πριν από τον τύπο («ισχυρό τετράγωνο»,
    # «a strong square», «ένα πολύ στενό τρίγωνο»)
    r"(?:(?:πολύ|αρκετά|ιδιαίτερα|ισχυρ\w*|στεν\w*|πλατ\w*|χαλαρ\w*|έντον\w*|"
    r"δυναμικ\w*|αρμονικ\w*|εύκολ\w*|δύσκολ\w*|κρίσιμ\w*|ακριβ\w*|σημαντικ\w*|"
    r"καθοριστικ\w*|βασικ\w*|κεντρικ\w*|εντυπωσιακ\w*|very|quite|strong|tight|close|"
    r"wide|loose|exact|harmonious|challenging|dynamic|tense|important|significant|"
    r"powerful|key|major|notable|striking)\s+){0,3}"
)
_GAP_C = re.compile(rf"^\s+{_VERB}({_ANY_ASPECT})\s+(?:(?:με|with|to|προς)\s+)?{_ART}$", re.IGNORECASE)
_PREFIX_B = re.compile(
    rf"({_ANY_ASPECT})\s+(?:(?:μεταξύ|ανάμεσα\s+σ\w*|between|of)\s+)?{_ART}$", re.IGNORECASE
)
_GAP_AB = re.compile(rf"^{_LINK}$", re.IGNORECASE)
_NEGATION = re.compile(
    r"(?<!\w)(?:δεν|μην|όχι|ούτε|χωρίς|καμία|κανένα|not|no|never|neither|nor|without)(?!\w)",
    re.IGNORECASE,
)
# v6: η άρνηση μετρά μόνο μέσα στην ΙΔΙΑ πρόταση-δήλωση (clause). Στο «Δεν
# είναι εύκολο, επειδή ο Ήλιος σχηματίζει τετράγωνο με τη Σελήνη» το «δεν»
# ανήκει στην κύρια πρόταση και ΔΕΝ αναιρεί την όψη.
_CLAUSE_BOUNDARY = re.compile(
    r"[,;:·\u0387(—–]|(?<!\w)(?:επειδή|γιατί|διότι|αλλά|ενώ|όμως|καθώς|ότι|πως|αφού|"
    r"because|but|while|since|that|although|whereas)(?!\w)",
    re.IGNORECASE,
)
_EXISTENCE_NEGATION = re.compile(
    r"(?<!\w)(?:δεν|μην)\s+(?:\w+\s+)?(?:υπάρχ|σχηματίζ|εμφανίζ|προκύπτ|ισχύ|επιβεβαιών)\w*"
    r"|(?<!\w)(?:does|do|did)\s+not\s+(?:exist|appear|occur|form|apply)"
    r"|(?<!\w)(?:is|are)\s+(?:not\s+present|absent|not\s+in\s+the\s+chart)",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[\r\n]|[.;!?](?:\s|$)")
_ORB_RE = re.compile(r"\d{1,2}\s*°\s*\d{1,2}\s*′")


def _name_matches(text: str) -> list[tuple[int, int, str]]:
    found = []
    for canonical, form in _NAME_FORMS.items():
        for m in re.finditer(rf"(?<!\w){form}(?!\w)", text, re.IGNORECASE):
            found.append((m.start(), m.end(), canonical))
    found.sort()
    result = []  # κράτα τη μακρύτερη ταύτιση όπου επικαλύπτονται
    for item in found:
        if result and item[0] < result[-1][1]:
            if item[1] - item[0] > result[-1][1] - result[-1][0]:
                result[-1] = item
            continue
        result.append(item)
    return result


# v9: η σύνταξη Γ δεν βασίζεται πλέον σε λίστα επιτρεπτών ρημάτων/επιθέτων
# («σχηματίζει», «ισχυρό» ...), που έπρεπε να επεκτείνεται σε κάθε γύρο.
# Γενικός κανόνας: ανάμεσα σε δύο διαδοχικά σημεία της ίδιας φράσης (χωρίς
# κόμμα, άνω τελεία, παρένθεση κ.λπ.) υπάρχει τύπος όψης, και μετά τον τύπο
# έως τρεις λέξεις («με τη», «with the») πριν από το δεύτερο σημείο.
_GAP_BREAK = re.compile(r"[,;:·\u0387()\[\]—–|]")
_GAP_TAIL = re.compile(rf"({_ANY_ASPECT})(?:\s+[^\s]+){{0,3}}\s+$", re.IGNORECASE)


_RELATIVE = re.compile(
    r"^\s*,\s*(?:(?:που|ο\s+οποίος|η\s+οποία|το\s+οποίο|οι\s+οποίοι|which|that|who)\s)?",
    re.IGNORECASE,
)


def _generic_gap_aspect(gap: str):
    # «Ο Άρης, που σχηματίζει τετράγωνο με τον Κρόνο» -- αναφορική πρόταση
    gap = re.sub(r"[ \t]+", " ", _RELATIVE.sub(" ", gap, count=1))
    if len(gap) > 90 or _GAP_BREAK.search(gap):
        return None
    m = _GAP_TAIL.search(gap)
    return _aspect_type(m.group(1)) if m else None


def _aspect_type(fragment: str):
    return next(
        (k for k, form in _ASPECT_FORMS.items() if re.search(form, fragment, re.IGNORECASE)),
        None,
    )


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    m = _SENTENCE_END.search(text, end)
    return left, (m.start() if m else len(text))


# ---------------------------------------------------------------------------
# v7: ΕΝΙΑΙΟΣ εξαγωγέας δηλώσεων όψης. Κάθε αναγνωρισμένη δήλωση -- σε πρόζα
# ή πίνακα, για γνωστό ή άγνωστο ζεύγος -- συγκρίνεται με τον χάρτη ως
#     ζεύγος -> τύπος -> δηλωμένο orb -> δηλωμένη βαρύτητα.
# Πριν, τα γνωστά ζεύγη παρακάμπτονταν εδώ, και οι παλαιότεροι έλεγχοι
# αναζητούσαν μόνο αν υπάρχει ΚΑΠΟΥ η σωστή αναφορά· μια πρόσθετη λανθασμένη
# δήλωση για το ίδιο ζεύγος δεν ελεγχόταν.
# Orb λαμβάνεται μόνο όταν δηλώνεται ρητά ως orb («orb 1°13′») ή ως πρώτο
# στοιχείο παρένθεσης αμέσως μετά τη δήλωση· έτσι μια θέση («στις 12°30′
# Λέοντα») δεν διαβάζεται ως orb. Βαρύτητα λαμβάνεται μόνο μέσα σε αυτή την
# παρένθεση ή σε δικό της κελί πίνακα.
# ---------------------------------------------------------------------------
_DMS = r"(\d{1,2})\s*°\s*(\d{1,2})\s*′"
_DEC = r"(\d{1,2}[.,]\d+)\s*°"  # v8: δεκαδικό orb («0.01°»)· απαιτεί δεκαδικό μέρος
_ORB_KEYED = re.compile(rf"\borb\s*[:=]?\s*(?:{_DMS}|{_DEC})", re.IGNORECASE)
_PAREN = re.compile(r"^\s*[,–—-]?\s*\(([^)]*)\)")
_PAREN_ORB = re.compile(rf"^\s*(?:orb\s*[:=]?\s*)?(?:{_DMS}|{_DEC})\s*(?:,|$)", re.IGNORECASE)


def _orb_value(m, offset=1) -> tuple[str, float, bool]:
    """(κείμενο, λεπτά τόξου, ακριβής_μορφή) από ταίριασμα _DMS|_DEC."""
    d, mi, dec = m.group(offset), m.group(offset + 1), m.group(offset + 2)
    if d is not None:
        return f"{int(d)}°{int(mi):02d}′", int(d) * 60 + int(mi), True
    value = float(dec.replace(",", "."))
    return f"{dec}°", value * 60, False


def _orb_differs(declared, a) -> bool:
    text, minutes, exact = declared
    if exact:
        return text != a.orb_text
    return abs(minutes - a.orb * 60) > 1.0  # δεκαδικό: ανοχή στρογγυλοποίησης 1′


def _weights_in(fragment: str) -> list[str]:
    return [k for k, form in _WEIGHT_FORMS.items() if re.search(form, fragment, re.IGNORECASE)]


def _claim_details(tail: str):
    """(όλα τα δηλωμένα orb, όλες οι δηλωμένες βαρύτητες) αμέσως μετά τη
    δήλωση. v8: επιστρέφονται ΟΛΕΣ οι τιμές -- δύο αντιφατικές τιμές δεν
    «ακυρώνουν» η μία την άλλη, ελέγχεται η καθεμία."""
    orbs, weights = [], []
    paren = _PAREN.match(tail)
    if paren:
        inner = paren.group(1)
        m = _PAREN_ORB.match(inner)
        if m:
            orbs.append(_orb_value(m))
        weights = _weights_in(inner)
    for m in _ORB_KEYED.finditer(tail):
        value = _orb_value(m)
        if value not in orbs:
            orbs.append(value)
    return orbs, weights


# v11: ελλειπτικό υποκείμενο. Στο «Η Σελήνη σχηματίζει τρίγωνο με τον Ερμή
# και τρίγωνο με την Αφροδίτη» το δεύτερο τρίγωνο ανήκει στη ΣΕΛΗΝΗ, όχι στον
# Ερμή. Όταν το κενό ανάμεσα σε δύο σημεία αρχίζει με σύνδεσμο και περιέχει
# τύπο όψης, η όψη αποδίδεται στο υποκείμενο της προηγούμενης δήλωσης της
# ίδιας πρότασης· αν δεν υπάρχει τέτοιο, η πρόταση θεωρείται αμφίσημη και
# ΔΕΝ παράγει δήλωση (αβεβαιότητα, όχι βέβαιο σφάλμα).
_COORD_START = re.compile(
    r"^\s*(?:,\s*)?(?:καθώς\s+και|όπως\s+και|και|ενώ|αλλά|as\s+well\s+as|and|while|but)\s",
    re.IGNORECASE,
)


# v13: «και τον», «και με τον», «καθώς και με τον», «and with the» ...
# Το σκέτο κόμμα επιτρέπεται μόνο ως απαρίθμηση («…, τον Ήλιο»)· το «, με τον
# Ήλιο …» είναι αμφίσημο (μπορεί να είναι συνοδευτική φράση) -> καμία δήλωση.
_OBJECT_COORD = re.compile(
    r"^\s*(?:(?:,\s*)?(?:καθώς\s+και|όπως\s+και|όσο\s+και|αλλά\s+και|και|as\s+well\s+as|but\s+also|and)"
    r"(?:\s*,?\s*(?:επίσης|επιπλέον|ακόμη|ακόμα|also)\s*,?)?\s+(?:(?:με|with)\s+)?"
    r"|,\s+)(?:(?:τον|την|τη|το|τους|the)\s+)?$",
    re.IGNORECASE,
)
# Ελληνικά: αιτιατική («και τον», «και με τον») = σίγουρα αντικείμενο, όποια
# κι αν είναι η συνέχεια. Αγγλικά: χωρίς πτώση, άρα η φράση πρέπει να
# τελειώνει μετά το όνομα ή να συνεχίζει με πρόθεση («in the natal chart»),
# όχι με ρήμα («and the Sun shines …»).
_GREEK_OBJECT = re.compile(r"(?:με|τον|την|τη|το|τους)\s+$", re.IGNORECASE)
_CLAUSE_TAIL_END = re.compile(
    r"^\s*(?:$|[,.;:·\u0387)(\n]|\s*(?:και|and)\s|(?:in|on|within|inside|at|of)\s)",
    re.IGNORECASE,
)


# v14: επεξηγηματικές (παρενθετικές) φράσεις μετά από σημείο.
#   «Η Σελήνη, κυβερνήτης του 8ου Οίκου, σχηματίζει τετράγωνο με τον Κρόνο»
#   «Ο Κρόνος, σε σύνοδο με τον Άρη, σχηματίζει εξάγωνο με τον Ποσειδώνα»
#   «… με τον Ερμή (πλανήτη της σκέψης) και με τον Κρόνο»
# Η φράση ανάμεσα στα δύο κόμματα (ή στην παρένθεση) διαβάζεται ΧΩΡΙΣΤΑ, με
# υποκείμενο το σημείο που επεξηγεί· η κύρια πρόταση διαβάζεται χωρίς αυτήν,
# ώστε το υποκείμενό της να μη «χάνεται» ούτε να αντικαθίσταται από σημείο
# της επεξήγησης. Η αντικατάσταση γίνεται με κενά ίδιου μήκους, άρα οι θέσεις
# χαρακτήρων (και τα αποσπάσματα των μηνυμάτων) μένουν ίδιες με το αρχικό.
_PAREN_COMMA = re.compile(
    rf"(?<!\w)(?P<name>{_ANY_NAME_ALT})(?!\w)(?P<body>\s*,(?P<c>[^,.;:·\u0387!?()\n|]{{3,110}}),)",
    re.IGNORECASE,
)
_PAREN_ROUND = re.compile(
    rf"(?<!\w)(?P<name>{_ANY_NAME_ALT})(?!\w)(?P<body>\s*\((?P<c>[^()\n|]{{2,110}})\))",
    re.IGNORECASE,
)
_ONLY_A_NAME = re.compile(
    rf"^\s*(?:(?:και|and)\s+)?(?:(?:ο|η|τον|την|τη|το|του|της|the)\s+)?(?:{_ANY_NAME_ALT})\s*$",
    re.IGNORECASE,
)
_COMMA_ADVERB = re.compile(
    r",\s*(?:επίσης|επιπλέον|παράλληλα|ταυτόχρονα|ωστόσο|μάλιστα|also|moreover|in\s+addition)\s*,",
    re.IGNORECASE,
)


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _split_parentheticals(text: str) -> tuple[str, list[str]]:
    """(κείμενο χωρίς επεξηγηματικές φράσεις, [«Σημείο φράση», …])."""
    for m in list(_COMMA_ADVERB.finditer(text)):
        text = _blank(text, m.start(), m.end())
    extras = []
    for pattern in (_PAREN_ROUND, _PAREN_COMMA):
        pos = 0
        while True:
            m = pattern.search(text, pos)
            if not m:
                break
            content = m.group("c")
            pos = m.end("name")
            if _ONLY_A_NAME.match(content):
                continue  # απαρίθμηση («τον Άρη, τον Κρόνο, και …»), όχι επεξήγηση
            if pattern is _PAREN_ROUND and (
                re.search(r"°|\borb\b", content, re.IGNORECASE) or _weights_in(content)
            ):
                continue  # τεχνική παρένθεση «(orb 1°13′, Στενή/ισχυρή)»
            if pattern is _PAREN_COMMA and re.match(
                r"\s*(?:και|ενώ|αλλά|όμως|and|while|but)\s", content, re.IGNORECASE
            ):
                continue  # νέα πρόταση, όχι επεξήγηση
            extras.append(f"{m.group('name')} {content.strip()}")
            text = _blank(text, m.start("body"), m.end("body"))
    return text, extras


def _prose_claims(text: str, _split: bool = True):
    original = text
    if _split:
        text, extras = _split_parentheticals(text)
        for extra in extras:
            for claim in _prose_claims(extra, _split=False):
                yield claim[:5] + (extra[:200],)
    names = _name_matches(text)
    prev_end = 0
    # v12: η τελευταία ΔΗΛΩΣΗ της πρότασης (υποκείμενο, αντικείμενο, τύπος,
    # όριο πρότασης). Ενημερώνεται σε κάθε δήλωση με ρητό υποκείμενο, ώστε
    # ένα νέο υποκείμενο («…, η Αφροδίτη σχηματίζει…») να αντικαθιστά το προηγούμενο.
    last = None
    gap_claim_end = None  # τέλος αντικειμένου δήλωσης που ο τύπος της ήταν ΣΤΟ κενό
    for i, ((s1, e1, n1), (s2, e2, n2)) in enumerate(zip(names, names[1:])):
        gap = text[e1:s2]
        left, right = _sentence_bounds(text, s1, e2)
        same_sentence = s2 < right and not _SENTENCE_END.search(gap)
        prefix = text[max(left, prev_end) : s1]
        prev_end = e1
        if not same_sentence:
            continue
        if n1 in ANGLE_NAMES and n2 in ANGLE_NAMES:
            continue
        next_start = names[i + 2][0] if i + 2 < len(names) else len(text)
        tail_end = min(right, next_start)
        aspect, claim_end = None, e2
        via_gap = False
        if re.match(rf"^{_DASH}$", gap):  # Α
            m = re.match(rf"^\s*[:—–-]?\s*\(?\s*({_ANY_ASPECT})", text[e2:tail_end], re.IGNORECASE)
            if m:
                aspect, claim_end = _aspect_type(m.group(1)), e2 + m.end()
        # Β. v14: όχι όταν ο τύπος του προθέματος ανήκει ήδη στην προηγούμενη
        # δήλωση («Mercury squares Jupiter and Pluto»: το «squares» είναι το
        # ρήμα του Ερμή, όχι «τετράγωνο Δία–Πλούτωνα»).
        if aspect is None and _GAP_AB.match(gap) and gap_claim_end != e1:
            m = _PREFIX_B.search(prefix)
            if m:
                aspect = _aspect_type(m.group(1))
        explicit_subject = True
        same_claim_sentence = last is not None and last[3] == left
        if aspect is None and _COORD_START.match(gap):  # ελλειπτικό υποκείμενο
            elliptic = _generic_gap_aspect(_COORD_START.sub(" ", gap, count=1))
            if elliptic and same_claim_sentence:
                n1, aspect, explicit_subject, via_gap = last[0], elliptic, False, True
            elif elliptic:
                continue  # αμφίσημο υποκείμενο: καμία δήλωση
        # v12: πολλά αντικείμενα με κοινό τύπο: «τρίγωνο με τον Ερμή και τον Ήλιο».
        # Μόνο αν το προηγούμενο σημείο ήταν το ΑΝΤΙΚΕΙΜΕΝΟ της τελευταίας
        # δήλωσης, ο σύνδεσμος δεν εισάγει νέο υποκείμενο (όχι «και ο/η»), και
        # η φράση τελειώνει μετά το νέο αντικείμενο.
        if (
            aspect is None
            and same_claim_sentence
            and last[1] == n1
            and _OBJECT_COORD.match(gap)
            and (_GREEK_OBJECT.search(gap) or _CLAUSE_TAIL_END.match(text[e2:right]))
        ):
            n1, aspect, explicit_subject, via_gap = last[0], last[2], False, True
        if aspect is None:  # Γ (v9: γενικό -- όχι λίστα ρημάτων/επιθέτων)
            aspect = _generic_gap_aspect(gap)
            via_gap = aspect is not None
        if aspect is None:
            continue
        # v14: «… μαζί με το εξάγωνο Ποσειδώνα–Πλούτωνα» -- το δεύτερο σημείο
        # ανοίγει δικό του ζεύγος με παύλα· δεν είναι «Ποσειδώνας–Ποσειδώνας».
        # (Η ρητή αυτο-όψη «Ο Ήλιος σχηματίζει τετράγωνο με τον Ήλιο» μένει σφάλμα.)
        if n1 == n2 and (
            not _split or re.match(rf"{_DASH}(?:{_ANY_NAME_ALT})", text[e2:], re.IGNORECASE)
        ):
            continue
        clause_start = left + max(
            (m.end() for m in _CLAUSE_BOUNDARY.finditer(text[left:s1])), default=0
        )
        if _NEGATION.search(text[clause_start:s2]):
            continue
        # «Η αντίθεση ανάμεσα στον Ήλιο και τη Σελήνη δεν υπάρχει»: άρνηση
        # ΥΠΑΡΞΗΣ μετά το ζεύγος, μέσα στην ίδια φράση.
        after = text[e2:tail_end]
        clause_end = min((m.start() for m in _CLAUSE_BOUNDARY.finditer(after)), default=len(after))
        if _EXISTENCE_NEGATION.search(after[:clause_end]):
            continue
        last = (n1 if explicit_subject else last[0], n2, aspect, left)
        gap_claim_end = e2 if via_gap else None
        orbs, weights = _claim_details(text[claim_end:tail_end])
        yield n1, n2, aspect, tuple(orbs), tuple(weights), " ".join(original[left:right].split())[:200]


def _aspect_claims(text: str):
    """Όλες οι ρητές δηλώσεις όψης του κειμένου, χωρίς διπλότυπα:
    (Α, Β, τύπος, (orb, …), (βαρύτητα, …), απόσπασμα)."""
    text = _normalize_prime_marks(text)
    seen, out = set(), []
    for claim in list(_prose_claims(text)) + list(_table_row_claims(text)):
        key = (frozenset(claim[:2]),) + tuple(claim[2:5])
        if key not in seen:
            seen.add(key)
            out.append(claim)
    return out


def _aspect_claim_problems(chart, text: str):
    """Επιστρέφει (undeclared, mismatched):
    undeclared: (Α, Β, τύπος, απόσπασμα) -- ζεύγος που δεν υπάρχει στον χάρτη.
    mismatched: (όψη χάρτη, περιγραφή διαφοράς, απόσπασμα) -- γνωστό ζεύγος
                με λάθος τύπο, orb ή βαρύτητα στη ΣΥΓΚΕΚΡΙΜΕΝΗ δήλωση."""
    by_pair = {frozenset((a.first, a.second)): a for a in chart.aspects}
    undeclared, mismatched = [], []
    for n1, n2, aspect, orbs, weights, snippet in _aspect_claims(text):
        a = by_pair.get(frozenset((n1, n2))) if n1 != n2 else None
        if a is None:
            undeclared.append((n1, n2, aspect, snippet))
            continue
        diffs = []
        if aspect != a.aspect:
            diffs.append(f"τύπος «{aspect}» αντί για «{a.aspect}»")
        for orb in orbs:
            if _orb_differs(orb, a):
                diffs.append(f"orb {orb[0]} αντί για {a.orb_text}")
        for weight in weights:
            if weight != a.weight:
                diffs.append(f"βαρύτητα «{weight}» αντί για «{a.weight}»")
        if diffs:
            mismatched.append((a, "; ".join(diffs), snippet))
    return undeclared, mismatched


# Συμβατότητα με παλαιότερα tests/κλήσεις.
def _undeclared_aspect_claims(chart, text: str):
    return _aspect_claim_problems(chart, text)[0]


# Γραμμές πίνακα. Ο reference_loader.docx_text() γράφει κάθε γραμμή πίνακα
# DOCX ως «κελί | κελί | …» -- η ίδια μορφή με το Παράρτημα και με πίνακες
# markdown. Μια γραμμή θεωρείται δήλωση όψης όταν τα κελιά της περιέχουν
# ΑΚΡΙΒΩΣ δύο σημεία (σε ένα κελί «Α–Β» ή σε δύο κελιά) και ΑΚΡΙΒΩΣ ένα κελί
# τύπου όψης (προαιρετικά με orb σε παρένθεση). Κελιά με πρόζα αγνοούνται
# εδώ (τα καλύπτει ο έλεγχος προτάσεων).
_CELL_NAMES = re.compile(
    rf"^{_ART}(?P<a>.+?)(?:\s*[–—/-]\s*{_ART}(?P<b>.+))?$", re.IGNORECASE
)
_CELL_ORB = re.compile(rf"^(?:orb\s*[:=]?\s*)?(?:{_DMS}|{_DEC})$", re.IGNORECASE)


def _cell_point_names(cell: str) -> list[str] | None:
    m = _CELL_NAMES.match(cell)
    if not m:
        return None
    names = []
    for part in (m.group("a"), m.group("b")):
        if part is None:
            continue
        hit = next(
            (k for k, f in _NAME_FORMS.items() if re.fullmatch(f, part.strip(), re.IGNORECASE)),
            None,
        )
        if hit is None:
            return None
        names.append(hit)
    return names


_CELL_LABEL = re.compile(
    r"^(?:Ζεύγος|Όψη|Τύπος(?:\s+όψης)?|Orb|Κατηγορία|Βαρύτητα|Pair|Aspect|Type|Category|Weight)\s*:\s*",
    re.IGNORECASE,
)


def _classify_row(line: str):
    """Αυστηρή ανάγνωση γραμμής πίνακα. Επιστρέφει (kind, payload):
      ("none", None)        -- δεν είναι γραμμή όψης (π.χ. πίνακας θέσεων)
      ("claim", claim)      -- πλήρως αναγνωσμένη γραμμή όψης
      ("malformed", λόγος)  -- μοιάζει με γραμμή όψης αλλά δεν διαβάζεται πλήρως
    v10: μια γραμμή γίνεται δεκτή ως δομημένη ΜΟΝΟ αν διαβάστηκε κάθε κελί
    της. Πριν, π.χ. το «orb = 0°01′» δεν διαβαζόταν, αλλά η γραμμή εξαιρούνταν
    από τον έλεγχο αριθμών -- η τιμή υπήρχε χωρίς να συγκρίνεται."""
    cells = [
        _CELL_LABEL.sub("", c.strip()) for c in _normalize_prime_marks(line).split("|") if c.strip()
    ]
    names, aspects, orbs, weights, other = [], [], [], [], []
    for cell in cells:
        hit = None
        for k, f in _ASPECT_FORMS.items():
            m = re.fullmatch(
                rf"{f}(?:\s*150°)?(?:\s*\(\s*(?:orb\s*[:=]?\s*)?(?:{_DMS}|{_DEC})\s*\))?",
                cell, re.IGNORECASE,
            )
            if m:
                hit = k
                if m.group(1) or m.group(3):
                    orbs.append(_orb_value(m))
                break
        if hit:
            aspects.append(hit)
            continue
        m = _CELL_ORB.match(cell)
        if m:
            orbs.append(_orb_value(m))
            continue
        cell_weights = _weights_in(cell)
        if cell_weights and re.fullmatch(rf"(?:{_ANY_WEIGHT}[\s,/;]*)+", cell, re.IGNORECASE):
            weights.extend(cell_weights)
            continue
        found = _cell_point_names(cell)
        if found:
            names.extend(found)
            continue
        other.append(cell)
    # Γραμμή όψης = τουλάχιστον δύο σημεία ΚΑΙ τύπος όψης ή orb.
    # (Πίνακας θέσεων «Ήλιος | Λέων | 12°30′» έχει ένα σημείο -> δεν είναι.)
    if len(names) < 2 or not (aspects or orbs):
        return "none", None
    if len(names) == 2 and names[0] == names[1]:
        return "malformed", f"το ίδιο σημείο ({names[0]}) δύο φορές"
    if len(names) != 2:
        return "malformed", f"{len(names)} σημεία αντί για ακριβώς 2"
    if len(aspects) != 1:
        return "malformed", ("λείπει ο τύπος όψης" if not aspects else f"{len(aspects)} τύποι όψης στην ίδια γραμμή")
    technical_other = [c for c in other if re.search(r"\d|orb", c, re.IGNORECASE) or _weights_in(c) or _aspect_type(c)]
    if technical_other:
        return "malformed", "μη αναγνώσιμο τεχνικό κελί: «" + technical_other[0] + "»"
    n1, n2 = names
    if n1 in ANGLE_NAMES and n2 in ANGLE_NAMES:
        return "none", None
    return "claim", (n1, n2, aspects[0], tuple(orbs), tuple(weights), line.strip())


def _table_row_claims(text: str):
    for line in text.splitlines():
        if "|" in line:
            kind, payload = _classify_row(line)
            if kind == "claim":
                yield payload






# ---------------------------------------------------------------------------
# v9: ΔΟΜΗΜΕΝΗ ΜΟΡΦΗ (Odigies v6, κανόνας 5).
# Κάθε όψη με αριθμητικά στοιχεία γράφεται ΜΟΝΟ σε δική της γραμμή:
#     Ήλιος–Σελήνη Τετράγωνο (orb 1°13′, Στενή/ισχυρή)
# (ή ως γραμμή πίνακα στο Παράρτημα). Η πρόζα ερμηνεύει χωρίς αριθμούς orb.
# Έτσι ο έλεγχος δεν χρειάζεται να μαντεύει διατυπώσεις: κάθε αριθμός τύπου
# «1°13′» / «0.5°» εκτός δομημένης γραμμής απορρίπτεται, εκτός αν είναι
# προφανώς ΘΕΣΗ (ακολουθεί/προηγείται ζώδιο) ή απόσταση από ακμή.
# ---------------------------------------------------------------------------
_ANY_NAME = "(?:" + "|".join(_NAME_FORMS.values()) + ")"
_ANY_WEIGHT = "(?:" + "|".join(_WEIGHT_FORMS.values()) + ")"
_STRUCTURED_LINE = re.compile(
    rf"^\s*(?:[-•*▪●]\s*)?{_ANY_NAME}\s*[–—-]\s*{_ANY_NAME}\s*:?\s*{_ANY_ASPECT}"
    rf"\s*\(\s*orb\s+\d{{1,2}}°\d{{2}}′\s*,\s*{_ANY_WEIGHT}\s*\)\s*\.?\s*$",
    re.IGNORECASE,
)
_TECH_VALUE = re.compile(rf"(?<![\d.,]){_DMS}|(?<![\d.,]){_DEC}")
_SIGN_WORD = (
    r"(?:Κρι\w*|Ταύρ\w*|Δίδυμ\w*|Διδύμ\w*|Καρκίν\w*|Λέ(?:ων|οντ\w*)|Παρθέν\w*|Ζυγ\w*|"
    r"Σκορπι\w*|Τοξότ\w*|Αιγόκερ\w*|Υδροχό\w*|Ιχθ\w*|Aries|Taurus|Gemini|Cancer|Leo|"
    r"Virgo|Libra|Scorpio|Sagittarius|Capricorn|Aquarius|Pisces)"
)
_POSITION_AFTER = re.compile(
    rf"^\s*(?:(?:του|της|των|στον|στην|στους|στο|in|of)\s+)?{_SIGN_WORD}", re.IGNORECASE
)
_POSITION_BEFORE = re.compile(rf"{_SIGN_WORD}\s*[,:]?\s*(?:στις\s+|at\s+)?$", re.IGNORECASE)
_CUSP_DISTANCE = re.compile(
    r"^\s*(?:από\s+(?:την\s+|τη\s+)?(?:επόμενη\s+)?ακμ\w*|πριν\s+από|before\s+the|"
    r"from\s+the\s+(?:next\s+)?cusp)",
    re.IGNORECASE,
)


def _is_structured(line: str) -> bool:
    if _STRUCTURED_LINE.match(_normalize_prime_marks(line)):
        return True
    if "|" not in line:
        return False
    kind, _ = _classify_row(line)
    if kind == "claim":
        return True
    # Πίνακας βασικών δεδομένων/ακμών (Odigies §12): «Ήλιος | Λέων | 12°30′».
    # Ο αριθμός είναι θέση· η γραμμή δεν είναι γραμμή όψης.
    if kind == "none":
        # v11: η εξαίρεση θέσης ΔΕΝ καλύπτει γραμμή με τύπο όψης ή «orb».
        if re.search(rf"\borb\b|{_ANY_ASPECT}", line, re.IGNORECASE):
            return False
        cells = [c.strip() for c in line.split("|")]
        return any(re.search(rf"(?<!\w){_SIGN_WORD}", c, re.IGNORECASE) for c in cells)
    return True  # malformed: αναφέρεται χωριστά, όχι δεύτερη φορά ως «αριθμός εκτός δομής»


def _stray_technical_values(text: str) -> list[tuple[str, str]]:
    """(τιμή, απόσπασμα) για αριθμούς τύπου orb ΕΚΤΟΣ δομημένης γραμμής."""
    found = []
    for line in _normalize_prime_marks(text).splitlines():
        if not _TECH_VALUE.search(line) or _is_structured(line):
            continue
        for m in _TECH_VALUE.finditer(line):
            after, before = line[m.end():], line[: m.start()]
            if _POSITION_AFTER.match(after) or _POSITION_BEFORE.search(before):
                continue  # θέση σε ζώδιο: «12°30′ Λέοντα», «Λέων 12°30′»
            if _CUSP_DISTANCE.match(after) or re.search(r"(?:απόσταση|distance)\s*(?:\w+\s+){0,2}$", before, re.I):
                continue  # απόσταση από ακμή
            found.append((m.group(0), line.strip()[:200]))
    return found


_PAIR_START = re.compile(
    rf"^\s*(?:[-•*▪●]\s*)?(?P<a>{_ANY_NAME})\s*[–—-]\s*(?P<b>{_ANY_NAME})(?!\w)", re.IGNORECASE
)


def _canonical(name_text: str):
    return next(
        (k for k, f in _NAME_FORMS.items() if re.fullmatch(f, name_text.strip(), re.IGNORECASE)), None
    )


def _malformed_aspect_rows(text: str) -> list[tuple[str, str]]:
    """Γραμμές όψεων (πίνακα ή «Α–Β …» με orb) που δεν διαβάζονται πλήρως."""
    out = []
    for line in _normalize_prime_marks(text).splitlines():
        if "|" in line:
            kind, payload = _classify_row(line)
            if kind == "malformed":
                out.append((payload, line.strip()[:200]))
            continue
        m = _PAIR_START.match(line)
        if not m or not (_TECH_VALUE.search(line) or re.search(r"\borb\b", line, re.I)):
            continue
        a, b = _canonical(m.group("a")), _canonical(m.group("b"))
        if a and a == b:
            out.append((f"το ίδιο σημείο ({a}) δύο φορές", line.strip()[:200]))
        elif not _STRUCTURED_LINE.match(line):
            out.append(("δεν ακολουθεί τη μορφή «Α–Β Τύπος (orb X°YY′, Κατηγορία)»", line.strip()[:200]))
    return out
