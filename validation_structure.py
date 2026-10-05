"""Έλεγχοι δομής: τμήματα ανά Οίκο, κυβερνήτες και πλαίσια σύνοψης, δηλώσεις τοποθέτησης πλανήτη σε Οίκο, μη δηλωμένα προσωπικά στοιχεία.

Μέρος του validator (βλ. validator.py για το ιστορικό και τη συνολική περιγραφή)."""

from __future__ import annotations
import re

from astrology import RULERS
import lexicon_en as EN
from validation_patterns import (
    _BOX_RULER_LINE,
    _HOUSE_HEADING_PATTERNS,
    _HOUSE_PATTERNS,
    _HOUSE_PATTERNS_ALT,
    _NAME_FORMS,
    _RULER_INTRO_PATTERNS,
    _name_pattern,
)


def _house_segments(text: str) -> dict[int, str]:
    """Εντοπίζει το τμήμα κειμένου κάθε Οίκου (από την επικεφαλίδα του μέχρι
    την επόμενη), με αναζήτηση με σειρά 1..12 ώστε να μην μπερδεύονται
    αριθμοί Οίκων που αναφέρονται εν παρόδω αλλού στο κείμενο."""
    starts = {}
    cursor = 0
    for n in range(1, 13):
        m = _HOUSE_HEADING_PATTERNS[n - 1].search(text, cursor)
        if not m:
            m = _HOUSE_PATTERNS[n - 1].search(text, cursor) or _HOUSE_PATTERNS_ALT[n - 1].search(
                text, cursor
            )
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
    rest = snippet[own.end() :] if own else snippet
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
    sentence = " ".join(text[left + 1 : right].split())
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
            m = _HOUSE_PATTERNS[n - 1].search(text, cursor) or _HOUSE_PATTERNS_ALT[n - 1].search(
                text, cursor
            )
        if m:
            starts.append((n, m.start()))
            cursor = m.start() + 1
    final = re.compile(r"Τελική συνθετική εικόνα|Final\s+synthesis").search(
        text, starts[-1][1] if starts else 0
    )
    tail_end = final.start() if final else len(text)
    bounds = []
    for i, (n, st) in enumerate(starts):
        en = starts[i + 1][1] if i + 1 < len(starts) else tail_end
        bounds.append((n, st, en))
    return bounds


_IC_BEFORE = re.compile(r"Πυθμέν\w*\s*$", re.IGNORECASE)


def _is_ic_mention(text: str, start: int) -> bool:
    """«Πυθμένας Ουρανού» είναι γωνία του χάρτη, όχι ο πλανήτης Ουρανός."""
    return bool(_IC_BEFORE.search(text[max(0, start - 20) : start]))


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
        # Αγγλικά: ρητό ρήμα θέσης ακολουθούμενο ΑΜΕΣΩΣ από «(the) Nth House»,
        # ή η σύντομη μορφή «Mars in the 7th House».
        numeric_en = re.compile(
            rf"{name}(?:[^.!?\n]{{0,90}}?{EN.PLACEMENT_VERBS}|,?)\s+(?:the\s+|your\s+)?"
            rf"(\d{{1,2}}){EN.ORDINAL_SUFFIX}?\s+House\b"
            rf"|{name},?\s+in\s+(?:the\s+|your\s+)?(\d{{1,2}}){EN.ORDINAL_SUFFIX}\s+House\b",
            re.IGNORECASE,
        )
        thematic_en = re.compile(
            rf"{name}[^.!?\n]{{0,70}}?{EN.PLACEMENT_VERBS}\s+the\s+(?:field|area|domain|sphere)\s+of\s+"
            rf"([^—.!?\n]{{2,55}})",
            re.IGNORECASE,
        )
        # v14: χωρίς ρήμα -- «Με τον Ήλιο στον 7ο Οίκο …», «Ο Άρης του 7ου Οίκου».
        # Μόνο όταν ο Οίκος ακολουθεί ΑΜΕΣΩΣ το όνομα.
        bare = re.compile(
            rf"(?<!\w){name}(?:\s+σου)?"
            rf"(?:,?\s+(?:που\s+βρίσκεται\s+)?στ(?:ον|ην|ους)\s+(?:{_SIGN_ACC_PLAIN})\s*(?:,\s*και|,|\s+και)?)?"
            rf"\s+(?P<prep>στον|του)\s+(\d{{1,2}})\s*(?:ος|ου|ο)?\s+Οίκ",
            re.IGNORECASE,
        )
        # «Mars, in Libra and in the 8th House» (πραγματικό αγγλικό έντυπο).
        bare_en = re.compile(
            rf"(?<!\w){name},?\s+(?:(?:which|who)\s+is\s+)?in\s+(?:{'|'.join(_SIGN_EN_NAMES_ALT)})"
            rf"\s*(?:,\s*and|,|\s+and)?\s+(?P<prep>in)\s+the\s+(\d{{1,2}})(?:st|nd|rd|th)\s+House",
            re.IGNORECASE,
        )
        bare_matches = list(bare_en.finditer(text)) + [
            m
            for m in bare.finditer(text)
            if m.group("prep").lower() == "στον"
            or not re.search(r"κυβερν\w*[^.!?\n]{0,30}$", text[max(0, m.start() - 45) : m.start()], re.IGNORECASE)
        ]
        numeric_matches = (
            list(numeric.finditer(text)) + list(numeric_en.finditer(text)) + bare_matches
        )
        thematic_matches = list(thematic.finditer(text)) + list(thematic_en.finditer(text))
        for match in numeric_matches:
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            if _is_ic_mention(text, match.start()):
                continue
            claimed = int(next(g for g in match.groups() if g and g.isdigit()))
            if 1 <= claimed <= 12 and claimed != point.house:
                context = _claim_context(text, match.start(), match.end(), bounds)
                if any(e[0] == point.name and e[1] == claimed and e[3] == context for e in errors):
                    continue  # η ίδια δήλωση από δύο μοτίβα
                errors.append(
                    (
                        point.name,
                        claimed,
                        point.house,
                        _claim_context(text, match.start(), match.end(), bounds),
                    )
                )
        for match in thematic_matches:
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            if _is_ic_mention(text, match.start()):
                continue
            label = match.group(1)
            claimed = next(
                (n for n, pat in theme_houses.items() if re.search(pat, label, re.IGNORECASE)), None
            ) or next(
                (n for n, pat in EN.THEME_HOUSES.items() if re.search(pat, label, re.IGNORECASE)),
                None,
            )
            if claimed and claimed != point.house:
                errors.append(
                    (
                        point.name,
                        claimed,
                        point.house,
                        _claim_context(text, match.start(), match.end(), bounds),
                    )
                )
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
    # v14: μόνο ΡΗΤΕΣ δηλώσεις για το πρόσωπο (β΄ πρόσωπο / κτητικό). Σκέτες
    # λέξεις όπως «καθηγητής», «teacher», «burnout», «ως μητέρα» είναι συνήθης
    # ερμηνευτική γλώσσα («ο Κρόνος σαν αυστηρός καθηγητής») και απέρριπταν
    # σωστές αναλύσεις.
    if not (personal.get("Επάγγελμα και σπουδές") or "").strip():
        checks.append(
            (
                "επάγγελμα/σπουδές",
                r"[^.!?\n]{0,45}(?:(?:είσαι|εργάζεσαι\s+ως|δουλεύεις\s+ως|η\s+δουλειά\s+σου\s+ως)\s+(?:καθηγήτρια|καθηγητής)"
                r"|διδασκαλία\s+(?:της\s+)?φυσικής|εργάζεσαι\s+σε\s+σχολ|έχεις\s+μεταπτυχιακό|το\s+πτυχίο\s+σου"
                r"|as\s+a\s+teacher,\s+you|you\s+(?:are|work\s+as)\s+a\s+teacher|teaching\s+physics"
                r"|you\s+work\s+(?:at|in)\s+a\s+school"
                r"|you\s+have\s+a\s+master'?s|your\s+(?:university\s+)?degree)[^.!?\n]{0,70}",
            )
        )
    if not (personal.get("Οικογενειακή κατάσταση") or "").strip():
        checks.append(
            (
                "οικογενειακή κατάσταση",
                r"[^.!?\n]{0,45}(?:με\s+(?:τα\s+)?δύο\s+(?:σου\s+)?παιδιά|έχεις\s+δύο\s+παιδιά"
                r"|(?:είσαι|ως)\s+(?:μητέρα|πατέρας)\s+(?:δύο|τριών|\d)|ο\s+σύζυγός\s+σου|η\s+σύζυγός\s+σου"
                r"|with\s+(?:your\s+)?two\s+children|you\s+have\s+two\s+children"
                r"|(?:you\s+are|as)\s+a\s+(?:mother|father)\s+of"
                r"|your\s+(?:husband|wife|spouse))[^.!?\n]{0,70}",
            )
        )
    if not (personal.get("Εργασιακές συνήθειες") or "").strip():
        checks.append(
            (
                "εργασιακές συνήθειες",
                r"[^.!?\n]{0,45}(?:επαγγελματική\s+σου\s+(?:κόπωση|εξουθένωση)|(?:το\s+)?burnout\s+(?:σου|που\s+(?:πέρασες|βιώνεις))"
                r"|your\s+(?:burnout|professional\s+exhaustion|work\s+fatigue))[^.!?\n]{0,70}",
            )
        )
    if not (personal.get("Έργα/ενδιαφέροντα") or "").strip():
        checks.append(
            (
                "έργα/στόχοι",
                r"[^.!?\n]{0,45}(?:θέλεις\s+να\s+αλλάξεις\s+καριέρα|το\s+έργο\s+σου\s+(?:στο|στην|με)"
                r"|you\s+want\s+to\s+change\s+careers?|your\s+project\s+(?:in|at|with))[^.!?\n]{0,70}",
            )
        )
    found = []
    for category, pattern in checks:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            found.append((category, match.group(0).strip()))
    return found


# ---------------------------------------------------------------------------
# Δηλώσεις «πλανήτης στο ζώδιο Χ»: ο validator έλεγχε μόνο τον Οίκο. Ένα
# λάθος ζώδιο («η Σελήνη στον Σκορπιό» ενώ είναι στον Ζυγό) περνούσε
# απαρατήρητο. Ελέγχεται κάθε μορφή «<σημείο> … στον/στην/στους <ζώδιο>».
# ---------------------------------------------------------------------------
_SIGN_ACCUSATIVE = {
    "Κριός": r"Κριό",
    "Ταύρος": r"Ταύρο",
    "Δίδυμοι": r"Διδύμους",
    "Καρκίνος": r"Καρκίνο",
    "Λέων": r"Λέοντα",
    "Παρθένος": r"Παρθένο",
    "Ζυγός": r"Ζυγό",
    "Σκορπιός": r"Σκορπιό",
    "Τοξότης": r"Τοξότη",
    "Αιγόκερως": r"Αιγόκερω(?:ς|)",
    "Υδροχόος": r"Υδροχόο",
    "Ιχθύες": r"Ιχθύες",
}
_SIGN_ALT = "|".join(f"(?P<s{i}>{p})" for i, p in enumerate(_SIGN_ACCUSATIVE.values()))
_SIGN_NAMES = list(_SIGN_ACCUSATIVE)
# Φράσεις που δείχνουν ότι το ζώδιο ΔΕΝ είναι η θέση του σημείου (Θεωρία των
# Μοιρών, χροιά, κυβέρνηση, ακμή/έκταση Οίκου, αντίθετο ζώδιο κ.λπ.).
_SIGN_NOT_PLACEMENT = re.compile(
    r"Μοιρ|μοίρα|αντιστοιχ|χροιά|κυβερν|ακμή|εκτείνεται|από\s+τ|έως|μέχρι|αντίθετ|απέναντι"
    r"|συνέχεια|τμήμα|εγκλωβισμ|ως\s+τ|προς\s+τ|ή\s+στ|κοντά",
    re.IGNORECASE,
)


_SIGN_GENITIVE = {
    "Κριός": r"Κριού",
    "Ταύρος": r"Ταύρου",
    "Δίδυμοι": r"Διδύμων",
    "Καρκίνος": r"Καρκίνου",
    "Λέων": r"Λέοντ(?:α|ος)",
    "Παρθένος": r"Παρθένου",
    "Ζυγός": r"Ζυγού",
    "Σκορπιός": r"Σκορπιού",
    "Τοξότης": r"Τοξότη",
    "Αιγόκερως": r"Αιγόκερω",
    "Υδροχόος": r"Υδροχόου",
    "Ιχθύες": r"Ιχθύων",
}
_SIGN_NOMINATIVE = {
    "Κριός": r"Κριός", "Ταύρος": r"Ταύρος", "Δίδυμοι": r"Δίδυμοι", "Καρκίνος": r"Καρκίνος",
    "Λέων": r"Λέων", "Παρθένος": r"Παρθένος", "Ζυγός": r"Ζυγός", "Σκορπιός": r"Σκορπιός",
    "Τοξότης": r"Τοξότης", "Αιγόκερως": r"Αιγόκερως", "Υδροχόος": r"Υδροχόος", "Ιχθύες": r"Ιχθύες",
}
_SIGN_GEN_ALT = "|".join(_SIGN_GENITIVE.values())
_SIGN_ACC_PLAIN = "|".join(_SIGN_ACCUSATIVE.values())
# Κάθε μορφή ζωδίου (ονομαστική, αιτιατική, γενική, αγγλικά).
_SIGN_ANY = "|".join(
    f"(?:{_SIGN_NOMINATIVE[k]}|{_SIGN_ACCUSATIVE[k]}|{_SIGN_GENITIVE[k]}|{EN.SIGN_NAMES[k]})"
    for k in _SIGN_ACCUSATIVE
)


def _sign_from_word(word: str):
    """Κανονικό (ελληνικό) όνομα ζωδίου από οποιαδήποτε μορφή του."""
    for canonical in _SIGN_ACCUSATIVE:
        forms = (
            f"(?:{_SIGN_NOMINATIVE[canonical]}|{_SIGN_ACCUSATIVE[canonical]}"
            f"|{_SIGN_GENITIVE[canonical]}|{EN.SIGN_NAMES[canonical]})"
        )
        if re.fullmatch(forms, word.strip(), re.IGNORECASE):
            return canonical
    return None


_SIGN_EN_NAMES_ALT = list(EN.SIGN_NAMES.values())
_SIGN_EN_NAMES = list(EN.SIGN_NAMES)  # ελληνικά κανονικά, ίδια σειρά με τα αγγλικά
_SIGN_EN_ALT = "|".join(f"(?P<e{i}>{en})" for i, en in enumerate(EN.SIGN_NAMES.values()))
_SIGN_NOT_PLACEMENT_EN = re.compile(EN.SIGN_NOT_PLACEMENT, re.IGNORECASE)


def _sign_claim_errors(chart, text: str) -> list[tuple[str, str, str, str]]:
    """(σημείο, δηλωμένο ζώδιο, σωστό ζώδιο, πλαίσιο) για κάθε λάθος ζώδιο."""
    errors = []
    bounds = _segments_bounds(text)
    for point in chart.points:
        if point.kind not in ("planet", "node", "angle") or not point.sign:
            continue
        pattern = re.compile(
            rf"{_name_pattern(point.name)}(?P<gap>[^.!?;\n]{{0,40}}?)\bστ(?:ον|ην|ους|ις|ο)\s+(?:{_SIGN_ALT})\b",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            gap = match.group("gap")
            if _is_ic_mention(text, match.start()) or _SIGN_NOT_PLACEMENT.search(gap):
                continue
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            index = next(i for i in range(len(_SIGN_NAMES)) if match.group(f"s{i}"))
            claimed = _SIGN_NAMES[index]
            if claimed != point.sign:
                errors.append(
                    (
                        point.name,
                        claimed,
                        point.sign,
                        _claim_context(text, match.start(), match.end(), bounds),
                    )
                )
        # v14: «στο ζώδιο του Λέοντα», «σε Λέοντα».
        pattern_extra = re.compile(
            rf"{_name_pattern(point.name)}(?P<gap>[^.!?;\n]{{0,40}}?)\b(?:"
            rf"στο\s+ζώδιο\s+τ(?:ου|ης|ων)\s+(?P<gen>{_SIGN_GEN_ALT})|σε\s+(?P<acc>{_SIGN_ACC_PLAIN}))\b",
            re.IGNORECASE,
        )
        for match in pattern_extra.finditer(text):
            gap = match.group("gap")
            if _is_ic_mention(text, match.start()) or _SIGN_NOT_PLACEMENT.search(gap):
                continue
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            claimed = _sign_from_word(match.group("gen") or match.group("acc"))
            context = _claim_context(text, match.start(), match.end(), bounds)
            if claimed and claimed != point.sign and not any(
                e[0] == point.name and e[3] == context for e in errors
            ):
                errors.append((point.name, claimed, point.sign, context))
        # Αγγλικά: «<σημείο> … in (the sign of) <ζώδιο>».
        pattern_en = re.compile(
            rf"{_name_pattern(point.name)}(?P<gap>[^.!?;\n]{{0,40}}?)\bin\s+(?:the\s+sign\s+of\s+)?"
            rf"(?:{_SIGN_EN_ALT})\b(?![-‑]|\s*-?\s*like\b|\s+(?:style|fashion|energy)\b)",
            re.IGNORECASE,
        )
        for match in pattern_en.finditer(text):
            if _SIGN_NOT_PLACEMENT_EN.search(match.group("gap")):
                continue
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            index = next(i for i in range(len(_SIGN_EN_NAMES)) if match.group(f"e{i}"))
            claimed = _SIGN_EN_NAMES[index]
            if claimed != point.sign:
                errors.append(
                    (
                        point.name,
                        claimed,
                        point.sign,
                        _claim_context(text, match.start(), match.end(), bounds),
                    )
                )
    return errors


# ---------------------------------------------------------------------------
# v4: ο κυβερνήτης ελέγχεται απέναντι στον ΠΡΑΓΜΑΤΙΚΟ χάρτη (ζώδιο ακμής),
# όχι μόνο για συνέπεια κειμένου–πλαισίου. Αν και τα δύο έγραφαν τον ίδιο
# λάθος πλανήτη, ο έλεγχος v3 περνούσε.
# ---------------------------------------------------------------------------
_LEADING_ARTICLE = re.compile(r"\s*(?:(?:ο|η|τον|την|του|της|the)\s+)?", re.IGNORECASE)
_NAME_SEPARATOR = re.compile(r"\s*(?:,|/|&|\bκαι\b|\band\b)\s*", re.IGNORECASE)


def _leading_ruler_names(box_text: str) -> list[str]:
    """Ονόματα στην ΑΡΧΗ της γραμμής «Κυβερνήτης: …» (π.χ. «Ποσειδώνας,
    Δίας» ή «ο Δίας / Ποσειδώνας»). Σταματά στην πρώτη λέξη που δεν είναι
    όνομα ή διαχωριστικό, ώστε ένα σχόλιο όπως «Δίας, σε τετράγωνο με Άρη»
    να μη θεωρηθεί ότι δηλώνει τον Άρη ως κυβερνήτη."""
    names, pos = [], 0
    while True:
        pos = _LEADING_ARTICLE.match(box_text, pos).end()
        hit = None
        for canonical, form in _NAME_FORMS.items():
            m = re.compile(rf"{form}(?!\w)", re.IGNORECASE).match(box_text, pos)
            if m and (hit is None or m.end() > hit[1]):
                hit = (canonical, m.end())
        if not hit:
            return names
        if hit[0] not in names:
            names.append(hit[0])
        pos = hit[1]
        sep = _NAME_SEPARATOR.match(box_text, pos)
        if not sep:
            return names
        pos = sep.end()


# v9: ο ρόλος (κύριος/παραδοσιακός) αναγνωρίζεται από τη λέξη-ρόλο και το
# ΠΛΗΣΙΕΣΤΕΡΟ όνομα πλανήτη μέσα στην ίδια φράση -- όχι από συγκεκριμένη
# σειρά λέξεων. Έτσι καλύπτονται εξίσου «Κύριος κυβερνήτης είναι ο Ουρανός»,
# «Ο Κρόνος είναι ο κύριος κυβερνήτης», «Ουρανός — παραδοσιακά Κρόνος» κ.λπ.
_ROLE_MODERN = re.compile(
    r"(?<!\w)(?:κύρι\w*|σύγχρον\w*)\s+(?:\w+\s+)?κυβερν\w*"
    r"|(?<!\w)(?:main|modern|primary|principal)\s+(?:\w+\s+)?ruler\w*",
    re.IGNORECASE,
)
_ROLE_TRAD = re.compile(r"(?<!\w)(?:παραδοσιακ\w*|traditional\w*|classical\w*)", re.IGNORECASE)
# v10: το κόμμα και η άνω-κάτω τελεία ΔΕΝ χωρίζουν όνομα από ρόλο
# («Κύριος κυβερνήτης: Κρόνος», «Ο Κρόνος, κύριος κυβερνήτης του Οίκου»).
# Χωρίζουν: τέλος πρότασης, άνω τελεία, παύλα, παρένθεση και σύνδεσμοι που
# εισάγουν ΑΛΛΟ υποκείμενο («και», «ενώ», «αλλά»). v11: ούτε η παρένθεση
# χωρίζει («Ο Κρόνος (κύριος κυβερνήτης)»).
_ROLE_SCOPE_BREAK = re.compile(
    r"[.;·\u0387\n—–]|(?<!\w)(?:και|ενώ|αλλά|όμως|and|while|but|whereas)(?!\w)",
    re.IGNORECASE,
)
_RULER_PLANETS = sorted({r for pair in RULERS.values() for r in pair if r})


def _phrase_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max((m.end() for m in _ROLE_SCOPE_BREAK.finditer(text, 0, start)), default=0)
    m = _ROLE_SCOPE_BREAK.search(text, end)
    return left, (m.start() if m else len(text))


def _ruler_claims_in_body(segment: str) -> list[tuple[str, str]]:
    """(όνομα, ρόλος) με ρόλο «κύριος» ή «παραδοσιακός»."""
    claims = []
    markers = [(m, "κύριος") for m in _ROLE_MODERN.finditer(segment)]
    markers += [(m, "παραδοσιακός") for m in _ROLE_TRAD.finditer(segment)]
    for m, role in markers:
        left, right = _phrase_bounds(segment, m.start(), m.end())
        best = None
        for name in _RULER_PLANETS:
            for nm in re.finditer(rf"(?<!\w){_NAME_FORMS[name]}(?!\w)", segment[left:right], re.IGNORECASE):
                ns, ne = left + nm.start(), left + nm.end()
                dist = m.start() - ne if ne <= m.start() else ns - m.end()
                if dist < 0:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, name)
        if best and (best[1], role) not in claims:
            claims.append((best[1], role))
    return claims


def _ruler_errors(chart, segments: dict[int, str]):
    """Επιστρέφει (wrong_ruler_claims, missing_ruler_box).
    wrong_ruler_claims: (Οίκος, δηλωμένος, αναμενόμενος, πού).
    Στο κυρίως κείμενο ελέγχεται και ο ΡΟΛΟΣ: ο κύριος πρέπει να είναι ο
    σύγχρονος κυβερνήτης του ζωδίου της ακμής, ο παραδοσιακός ο παραδοσιακός
    (όπου δεν υπάρχει ξεχωριστός, ο ίδιος με τον κύριο). Στο πλαίσιο σύνοψης
    ελέγχεται μόνο ότι κάθε όνομα ανήκει στους κυβερνήτες της ακμής."""
    wrong, missing_box = [], []
    for n in range(1, 13):
        segment = segments.get(n)
        if not segment:
            continue  # ήδη καταγράφηκε στο missing_houses
        modern, traditional = RULERS[chart.cusps[n - 1].sign]
        allowed = [r for r in (modern, traditional) if r]
        for name, role in _ruler_claims_in_body(_BOX_RULER_LINE.sub("", segment)):
            expected = modern if role == "κύριος" else (traditional or modern)
            if name != expected:
                wrong.append((n, name, expected, f"κείμενο ({role})"))
        box_text = _box_ruler_text(segment)
        box_names = _leading_ruler_names(box_text) if box_text is not None else []
        if not box_names:
            missing_box.append(n)
            continue
        for name in box_names:
            if name not in allowed:
                wrong.append((n, name, " / ".join(allowed), "πλαίσιο"))
        # v8 (Odigies §3): στο πλαίσιο σύνοψης πρώτα ο σύγχρονος κυβερνήτης.
        if box_names and modern in box_names and box_names[0] != modern:
            wrong.append((n, f"(σειρά) {box_names[0]} πρώτος", modern, "πλαίσιο"))
        # v8 (Odigies §3 και ενότητα Οίκου): και το ΚΥΡΙΩΣ ΚΕΙΜΕΝΟ πρέπει να
        # ονομάζει κάθε κυβερνήτη ως κυβερνήτη. Ελαστική σύνταξη: το όνομα
        # αρκεί να βρίσκεται στην ίδια πρόταση με «κυβερνήτ…»/«ruler», όχι
        # σε συγκεκριμένη φράση. Η γραμμή του πλαισίου δεν μετράει εδώ.
        body = _BOX_RULER_LINE.sub("", segment)
        for name in allowed:
            if not _named_as_ruler(body, name):
                wrong.append((n, f"(λείπει) {name}", " / ".join(allowed), "κυρίως κείμενο"))
        # v7: το πλαίσιο πρέπει να δηλώνει ΟΛΟΥΣ τους κυβερνήτες της ακμής
        # (σύγχρονο και, όπου υπάρχει, παραδοσιακό) -- όχι μόνο επιτρεπτά ονόματα.
        for name in allowed:
            if name not in box_names:
                wrong.append((n, f"(λείπει) {name}", " / ".join(allowed), "πλαίσιο"))
    return wrong, missing_box


# v10: και η λέξη-ρόλο «παραδοσιακά» μετρά ως δήλωση κυβερνήτη -- η ίδια η
# διατύπωση των οδηγιών είναι «Υδροχόος: Ουρανός — παραδοσιακά Κρόνος».
_RULER_WORD = r"(?:κυβερν\w*|παραδοσιακ\w*|rul(?:er|ers|ed|es|ing)\b|traditional\w*)"


def _named_as_ruler(body: str, name: str) -> bool:
    form = _NAME_FORMS[name]
    pattern = (
        rf"{_RULER_WORD}[^.;\n]{{0,100}}?(?<!\w){form}(?!\w)"
        rf"|(?<!\w){form}(?!\w)[^.;\n]{{0,100}}?{_RULER_WORD}"
    )
    return re.search(pattern, body, re.IGNORECASE) is not None


# ---------------------------------------------------------------------------
# v14: δηλώσεις δεδομένων που δεν συγκρίνονταν με τον χάρτη:
#   * μοίρες θέσης («Ο Ήλιος βρίσκεται στις 15°00′ του Υδροχόου»),
#   * ζώδιο ακμής Οίκου («Η ακμή του Οίκου βρίσκεται στον Σκορπιό»),
#   * ανάδρομη/ορθόδρομη κίνηση («Ο Άρης είναι ανάδρομος»).
# Επιστρέφουν (περιγραφή διαφοράς, πλαίσιο).
# ---------------------------------------------------------------------------
_DEG = r"(\d{1,2})\s*°\s*(\d{1,2})\s*′"
_POSITION_SKIP = re.compile(r"ακμ|cusp|κυβερν|rul|\borb\b|απόστασ|distance", re.IGNORECASE)


def _position_claim_errors(chart, text: str) -> list[tuple[str, str]]:
    errors, bounds = [], _segments_bounds(text)
    for point in chart.points:
        if point.kind not in ("planet", "node", "angle") or not point.sign:
            continue
        name = _name_pattern(point.name)
        after = re.compile(  # «Ήλιος … 21°14′ (του) Υδροχόου»
            rf"(?<!\w){name}(?!\w)(?P<gap>[^.!?;\n\d]{{0,45}}?){_DEG}(?:\s*\d{{1,2}}\s*″)?\s*"
            rf"(?:(?:του|της|των|στον|στην|στους|in|of)\s+)?(?P<sign>{_SIGN_ANY})(?!\w)",
            re.IGNORECASE,
        )
        before = re.compile(  # «Ήλιος: Υδροχόος 21°14′», «Ήλιος | Υδροχόος | 21°14′»
            rf"(?<!\w){name}(?!\w)(?P<gap>[^.!?;\n\d]{{0,25}}?)(?<!\w)(?P<sign>{_SIGN_ANY})(?!\w)"
            rf"[ \t,:|]*(?:στις[ \t]+|at[ \t]+)?{_DEG}",
            re.IGNORECASE,
        )
        for pattern in (after, before):
            for m in pattern.finditer(text):
                gap = m.group("gap")
                if _POSITION_SKIP.search(gap) or _is_ic_mention(text, m.start()):
                    continue
                if _claim_belongs_to_other_point(m.group(0), point.name):
                    continue
                nums = [g for g in m.groups() if g and g.isdigit()]
                degree, minute = int(nums[0]), int(nums[1])
                sign = _sign_from_word(m.group("sign"))
                actual = point.degree * 60 + point.minute
                if sign == point.sign and abs(degree * 60 + minute - actual) <= 1:
                    continue
                if sign != point.sign and any(
                    _name_pattern(p.name) and p.sign == sign
                    and abs(degree * 60 + minute - (p.degree * 60 + p.minute)) <= 1
                    for p in list(chart.points) + list(chart.cusps)
                ):
                    continue  # η θέση ανήκει σε άλλο σημείο/ακμή της ίδιας γραμμής
                context = _claim_context(text, m.start(), m.end(), bounds)
                item = (
                    f"Λανθασμένη θέση — {point.name}: το κείμενο γράφει {degree}°{minute:02d}′ {sign}, "
                    f"ενώ τα ελεγμένα δεδομένα δίνουν {point.degree}°{point.minute:02d}′ {point.sign}",
                    context,
                )
                if item not in errors:
                    errors.append(item)
    return errors


_CUSP_SIGN = re.compile(
    rf"(?:(?<!\w)(?:ακμή|cusp)(?!\w)[^.!?;\n\d]{{0,40}}?"
    rf"|(?:Οίκος|House)\s+(?:ξεκιν\w+|αρχίζ\w+|begins|starts)\s+)"
    rf"(?:στ(?:ον|ην|ους)|in)\s+(?P<sign>{_SIGN_ANY})(?!\w)",
    re.IGNORECASE,
)


def _cusp_sign_errors(chart, text: str) -> list[tuple[str, str]]:
    errors, bounds = [], _segments_bounds(text)
    if len(getattr(chart, "cusps", None) or []) < 12:
        return errors
    for n, start, end in bounds:
        allowed = {chart.cusps[n - 1].sign, chart.cusps[n % 12].sign}
        for m in _CUSP_SIGN.finditer(text, start, end):
            if re.search(r"επόμεν|προηγούμεν|next|previous|απέναντι|opposite", m.group(0), re.IGNORECASE):
                continue
            sign = _sign_from_word(m.group("sign"))
            if sign and sign not in allowed:
                errors.append(
                    (
                        f"Λανθασμένο ζώδιο ακμής — {n}ος Οίκος: το κείμενο γράφει {sign}, "
                        f"ενώ η ακμή του είναι στον/στην {chart.cusps[n - 1].sign}",
                        _claim_context(text, m.start(), m.end(), bounds),
                    )
                )
    return errors


_RETRO = r"(?P<adj>ανάδρομ\w+|ορθόδρομ\w+|retrograde)"


def _retrograde_claim_errors(chart, text: str) -> list[tuple[str, str]]:
    """«Ο Άρης είναι ανάδρομος», «ο ανάδρομος Άρης», «Mars is retrograde»."""
    errors, bounds = [], _segments_bounds(text)
    any_name = "|".join(_NAME_FORMS.values())
    for point in chart.points:
        if point.kind != "planet":
            continue  # Δεσμοί/γωνίες: δεν ελέγχονται
        name = _name_pattern(point.name)
        patterns = [
            # επίθετο ΠΡΙΝ: «ο ανάδρομος Άρης», «η ανάδρομη κίνηση του Άρη», «retrograde Mars»
            re.compile(
                rf"{_RETRO}[ \t]+(?:(?:κίνηση|πορεία|φάση|motion)[ \t]+(?:του|της|of)[ \t]+)?(?<!\w){name}(?!\w)",
                re.IGNORECASE,
            ),
            # επίθετο ΜΕΤΑ: «Ο Άρης είναι ανάδρομος», «Ο Άρης (ανάδρομος)», «Mars is retrograde»
            re.compile(
                rf"(?<!\w){name}(?!\w)[ \t(,]+(?:(?:είναι|κινείται|βρίσκεται|παραμένει|is|moves|was)[ \t]+)?"
                rf"(?:(?:σε|in)[ \t]+)?{_RETRO}(?![ \t]+(?:(?:κίνηση|πορεία|φάση|motion)[ \t]+(?:του|της|of)[ \t]+)?(?:{any_name}))",
                re.IGNORECASE,
            ),
        ]
        for pattern in patterns:
            for m in pattern.finditer(text):
                if _is_ic_mention(text, m.start()):
                    continue
                claimed_retro = not m.group("adj").lower().startswith("ορθ")
                if claimed_retro == bool(point.retrograde):
                    continue
                item = (
                    f"Λανθασμένη κίνηση — {point.name}: το κείμενο γράφει "
                    f"«{'ανάδρομος' if claimed_retro else 'ορθόδρομος'}», ενώ τα ελεγμένα δεδομένα δίνουν "
                    f"«{'ανάδρομος' if point.retrograde else 'ορθόδρομος'}»",
                    _claim_context(text, m.start(), m.end(), bounds),
                )
                if item not in errors:
                    errors.append(item)
    return errors


def _data_claim_errors(chart, text: str) -> list[tuple[str, str]]:
    return (
        _position_claim_errors(chart, text)
        + _cusp_sign_errors(chart, text)
        + _retrograde_claim_errors(chart, text)
    )


def _ruler_role_errors(chart, text: str) -> list[tuple[int, str, str, str]]:
    """Για το τελικό έντυπο: (Οίκος, δηλωμένος, αναμενόμενοι, πού). Ελέγχεται
    μόνο ότι όποιος ονομάζεται ρητά «κύριος/σύγχρονος/παραδοσιακός κυβερνήτης»
    μέσα σε έναν Οίκο είναι πράγματι κυβερνήτης του ζωδίου της ακμής του."""
    wrong = []
    if len(getattr(chart, "cusps", None) or []) < 12:
        return wrong
    for n, start, end in _segments_bounds(text):
        modern, traditional = RULERS[chart.cusps[n - 1].sign]
        allowed = [r for r in (modern, traditional) if r]
        for name, role in _ruler_claims_in_body(text[start:end]):
            if name not in allowed:
                wrong.append((n, name, " / ".join(allowed), f"κείμενο ({role})"))
    return wrong
