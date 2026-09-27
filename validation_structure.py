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
        numeric_matches = list(numeric.finditer(text)) + list(numeric_en.finditer(text))
        thematic_matches = list(thematic.finditer(text)) + list(thematic_en.finditer(text))
        for match in numeric_matches:
            if _claim_belongs_to_other_point(match.group(0), point.name):
                continue
            if _is_ic_mention(text, match.start()):
                continue
            claimed = int(next(g for g in match.groups() if g))
            if 1 <= claimed <= 12 and claimed != point.house:
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
    if not (personal.get("Επάγγελμα και σπουδές") or "").strip():
        checks.append(
            (
                "επάγγελμα/σπουδές",
                r"[^.!?\n]{0,45}(?:καθηγήτρια|καθηγητής|διδασκαλία\s+(?:της\s+)?φυσικής|στο\s+επάγγελμά\s+σου|εργάζεσαι\s+σε\s+σχολ|έχεις\s+μεταπτυχιακό|το\s+πτυχίο\s+σου"
                r"|\bteacher\b|teaching\s+physics|in\s+your\s+(?:job|profession)|you\s+work\s+(?:at|in)\s+a\s+school"
                r"|you\s+have\s+a\s+master'?s|your\s+(?:university\s+)?degree)[^.!?\n]{0,70}",
            )
        )
    if not (personal.get("Οικογενειακή κατάσταση") or "").strip():
        checks.append(
            (
                "οικογενειακή κατάσταση",
                r"[^.!?\n]{0,45}(?:με\s+(?:τα\s+)?δύο\s+(?:σου\s+)?παιδιά|έχεις\s+δύο\s+παιδιά|ως\s+μητέρα|ως\s+πατέρας|ο\s+σύζυγός\s+σου|η\s+σύζυγός\s+σου"
                r"|with\s+(?:your\s+)?two\s+children|you\s+have\s+two\s+children|as\s+a\s+(?:mother|father)"
                r"|your\s+(?:husband|wife|spouse))[^.!?\n]{0,70}",
            )
        )
    if not (personal.get("Εργασιακές συνήθειες") or "").strip():
        checks.append(
            (
                "εργασιακές συνήθειες",
                r"[^.!?\n]{0,45}(?:επαγγελματική\s+κόπωση|επαγγελματική\s+εξουθένωση|burnout|professional\s+exhaustion|work\s+fatigue)[^.!?\n]{0,70}",
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
