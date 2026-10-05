"""Ο έλεγχος του τελικού εντύπου πελάτη (validate_rewrite): χωρίς τεχνικά αστρολογικά δεδομένα.

Μέρος του validator (βλ. validator.py για το ιστορικό και τη συνολική περιγραφή)."""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from validation_patterns import (
    _HOUSE_HEADING_PATTERNS,
    _HOUSE_PATTERNS,
    _HOUSE_PATTERNS_ALT,
    _HOUSE_WORD_PATTERNS,
    _NAME_FORMS,
    _SECTION_PATTERNS,
    _has_section,
    _name_pattern,
    _normalize_prime_marks,
    _section_heading_re,
)
import lexicon_en as EN
from validation_aspects import _aspect_claim_problems
from validation_structure import (
    _data_claim_errors,
    _ruler_role_errors,
    _location_claim_errors,
    _sign_claim_errors,
    _unauthorized_personal_claims,
)

# Η τελική αναδιατύπωση είναι το έντυπο που βλέπει ο πελάτης. ΔΕΝ πρέπει να
# περιέχει τεχνικά αστρολογικά δεδομένα: μοίρες, orb, κατηγορίες βαρύτητας,
# πίνακα/Παράρτημα όψεων ή ενδείξεις πηγής. Τα τεχνικά στοιχεία μένουν στο
# ελεγμένο τεχνικό Word (validate_analysis), που τα περιέχει αυτούσια.
#
# Παλαιότερα το έντυπο έκλεινε υποχρεωτικά με την πρόταση «Αυτή η ανάλυση
# βασίζεται σε πλήρη μαθηματικό έλεγχο…». Καταργήθηκε: μπορούσε να διαβαστεί
# ως επιστημονική επικύρωση της ερμηνείας. Τώρα ο κανόνας 19 ορίζει ότι δεν
# μπαίνει καμία τέτοια πρόταση, και αν εμφανιστεί σημειώνεται για αφαίρεση.


_CLIENT_TECHNICAL_PATTERNS = [
    ("μοίρες/λεπτά", re.compile(r"\d{1,3}\s*°(?:\s*\d{1,2}\s*′)?(?:\s*\d{1,2}\s*″)?")),
    ("orb", re.compile(r"(?<![A-Za-z])orb(?![A-Za-z])", re.IGNORECASE)),
    (
        "κατηγορία βαρύτητας",
        re.compile(
            r"Στενή\s*/\s*ισχυρή|Πλατιά\s+αλλά\s+έγκυρη|Πολύ\s+πλατιά\s*/\s*δευτερεύουσα|"
            + EN.CLIENT_WEIGHT_REGEX,
            re.IGNORECASE,
        ),
    ),
    (
        "Παράρτημα/πίνακας όψεων",
        re.compile(
            r"(?m)^\s*(?:Τεχνικό\s+)?Παράρτημα\b|Παράρτημα[^\r\n]{0,90}επιβεβαιωμέν\w*[^\r\n]{0,40}όψε(?:ων|ις)|"
            + EN.CLIENT_APPENDIX_REGEX,
            re.IGNORECASE,
        ),
    ),
    (
        "ένδειξη τεχνικής πηγής",
        re.compile(
            r"Πίνακας\s+Astrodienst|Μαθηματική\s+παραγωγή\s+από\s+τον\s+άξονα|" + EN.CLIENT_SOURCE_REGEX,
            re.IGNORECASE,
        ),
    ),
    (
        "πρόταση μαθηματικού ελέγχου (κανόνας 19)",
        re.compile(
            r"βασίζεται\s+σε\s+(?:πλήρη\s+)?μαθηματικό\s+έλεγχο|τεχνικά\s+στοιχεία\s+είναι\s+διαθέσιμα|"
            + EN.CLIENT_CHECK_SENTENCE_REGEX,
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Ουσία ανά Οίκο και ανά ενότητα
# ---------------------------------------------------------------------------
# Περιστατικό (κριτική v10): ένα «έντυπο» με ΜΟΝΟ τους 12 τίτλους Οίκων, χωρίς
# καμία ανάλυση, περνούσε τον έλεγχο. Ο έλεγχος διαπίστωνε μόνο ότι οι τίτλοι
# υπάρχουν. Τώρα κάθε Οίκος και κάθε ενότητα πρέπει να έχει ουσιαστικό κείμενο,
# κάθε Οίκος να κλείνει με «Κεντρικό θέμα:» (κανόνας 15), και κάθε πλανήτης
# ή Δεσμός που βρίσκεται σε έναν Οίκο να κατονομάζεται μέσα στο κεφάλαιό του
# (κανόνας 7). Τα όρια είναι εδώ, για εύκολη ρύθμιση.
# Το απόλυτο ελάχιστο είναι σκόπιμα χαμηλό (≈ μία σύντομη παράγραφος): ο
# κανόνας 18 ζητά οι απλοί Οίκοι να μένουν σύντομοι και να μην επιμηκύνονται
# τεχνητά. Το ουσιαστικό όριο είναι το ποσοστό της πηγής, που μεγαλώνει μόνο
# για τους Οίκους με πλούσια ελεγμένη ερμηνεία.
MIN_HOUSE_WORDS = 25  # ελάχιστες λέξεις κειμένου σε κάθε Οίκο
MIN_HOUSE_SHARE = 0.20  # και τουλάχιστον 20% της ερμηνευτικής έκτασης της πηγής
MIN_SECTION_WORDS = 40  # ελάχιστες λέξεις σε κάθε τελική ενότητα

_CENTRAL_THEME = re.compile(r"Κεντρικ\w*\s+θέμα\s*:|Central\s+theme\s*:", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+")
# Γραμμές της τεχνικής πηγής που ΔΕΝ είναι ερμηνεία: όψεις με orb, γραμμές
# πίνακα, πλαίσιο σύνοψης. Δεν μετράνε στην «ερμηνευτική έκταση» της πηγής.
_SOURCE_NON_PROSE = re.compile(
    r"\borb\b|\||^\s*(?:Βασική\s+δύναμη|Βασική\s+πρόκληση|Κυβερνήτης|Τελικό\s+συμπέρασμα"
    r"|Key\s+strength|Key\s+challenge|Ruler|Final\s+conclusion)\s*:",
    re.IGNORECASE,
)


def _words(text: str) -> int:
    return len(_WORD.findall(text))


def _prose_words(text: str) -> int:
    return sum(_words(l) for l in text.splitlines() if not _SOURCE_NON_PROSE.search(l))


_TRACKED_SECTIONS = [s for s in _SECTION_PATTERNS if not s.startswith("Παράρτημα")]


def _section_starts(text: str, after: int = 0) -> dict[str, int]:
    """Θέση του τίτλου κάθε τελικής ενότητας (μετά από τη θέση `after`)."""
    starts = {}
    for section in list(_SECTION_PATTERNS):
        m = _section_heading_re(section).search(text, after) or re.compile(
            _SECTION_PATTERNS[section], re.IGNORECASE
        ).search(text, after)
        if m:
            starts[section] = m.start()
    return starts


def _document_parts(text: str):
    """(σώματα Οίκων, σώματα ενοτήτων): το κείμενο κάθε Οίκου ΧΩΡΙΣ τη γραμμή
    τίτλου, και κάθε τελικής ενότητας. Ο 12ος Οίκος σταματά πριν από την
    πρώτη τελική ενότητα -- αλλιώς θα «δανειζόταν» το κείμενό τους."""
    starts, cursor = [], 0
    for n in range(1, 13):
        m = _HOUSE_HEADING_PATTERNS[n - 1].search(text, cursor)
        if not m:
            m = _HOUSE_PATTERNS[n - 1].search(text, cursor) or _HOUSE_PATTERNS_ALT[n - 1].search(
                text, cursor
            )
        if m:
            starts.append(("house", n, m.start()))
            cursor = m.start() + 1
    last_house = starts[-1][2] if starts else 0
    for section, pos in _section_starts(text, last_house + 1 if starts else 0).items():
        starts.append(("section", section, pos))
    starts.sort(key=lambda item: item[2])
    houses, sections = {}, {}
    for i, (kind, key, pos) in enumerate(starts):
        end = starts[i + 1][2] if i + 1 < len(starts) else len(text)
        chunk = text[pos:end]
        newline = chunk.find("\n")
        body = chunk[newline + 1 :] if newline != -1 else ""
        (houses if kind == "house" else sections)[key] = body
    return houses, sections


# ---------------------------------------------------------------------------
# Επανάληψη του ίδιου κειμένου σε πολλούς Οίκους
# ---------------------------------------------------------------------------
# Περιστατικό (κριτική v11): η ίδια γενική παράγραφος σε όλους τους Οίκους,
# με τα απαιτούμενα ονόματα πλανητών και «Κεντρικό θέμα», περνούσε τον έλεγχο.
# Ο κανόνας 9 απαγορεύει να ξαναγράφεται αυτούσιο το ίδιο κείμενο σε κάθε
# κεφάλαιο.
#
# Κριτική v12: μία μόνο κοινή πρόταση σε δύο Οίκους δεν πρέπει να κλειδώνει τη
# λήψη -- μπορεί να είναι θεμιτή (π.χ. μια κοινή διατύπωση). Γι' αυτό:
#   * ΑΠΟΡΡΙΨΗ όταν το κοινό κείμενο δύο Οίκων αποτελεί ≥ 40% του μικρότερου
#     ΚΑΙ είναι ουσιαστικό σε όγκο: είτε ≥ 2 κοινές προτάσεις, είτε ≥ 20 κοινές
#     λέξεις (π.χ. μία μεγάλη αντιγραμμένη παράγραφος-πρόταση),
#   * μικρή κοινή πρόταση → μόνο ΠΡΟΕΙΔΟΠΟΙΗΣΗ προς ανάγνωση, χωρίς κλείδωμα.
#
# Κριτική v14: η ίδια παράγραφος ~35 λέξεων (μία πρόταση) σε όλους τους Οίκους
# περνούσε με 66 προειδοποιήσεις (μία ανά ζεύγος). Τώρα απορρίπτεται λόγω
# όγκου, και οι προειδοποιήσεις ομαδοποιούνται: ΜΙΑ ανά επαναλαμβανόμενη
# πρόταση, με όλους τους Οίκους όπου εμφανίζεται.
# Πριν τη σύγκριση αφαιρούνται ονόματα σημείων, ζωδίων και αριθμοί, ώστε να
# μη «σώζει» η απλή αλλαγή ονόματος. «Σχεδόν ίδια» = ≥ 70% κοινές λέξεις.
REPEAT_MIN_WORDS = 8  # μικρότερες προτάσεις δεν συγκρίνονται
SIMILAR_SENTENCE = 0.70  # ομοιότητα λέξεων για «σχεδόν ίδια» πρόταση
MAX_SHARED_SHARE = 0.40  # για απόρριψη: κοινό μέρος του μικρότερου Οίκου
MIN_SHARED_SENTENCES = 2  # ... και τουλάχιστον τόσες κοινές προτάσεις
MIN_SHARED_WORDS = 20  # ... ή τουλάχιστον τόσες κοινές λέξεις

_SENTENCE_SPLIT = re.compile(r"(?<=[.!;;?])\s+|\n+")


def _neutral_words(text: str) -> list[str]:
    """Λέξεις χωρίς ονόματα σημείων/ζωδίων και αριθμούς, σε πεζά."""
    from astrology import SIGNS

    for pattern in _NAME_FORMS.values():
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    for sign in list(SIGNS) + list(EN.SIGN_NAMES.values()):
        text = re.sub(re.escape(sign[:-2] if len(sign) > 4 else sign) + r"\w*", " ", text, flags=re.IGNORECASE)
    return [w.lower() for w in _WORD.findall(text)]


def _house_sentences(body: str) -> tuple[list[tuple[set, int, str]], int]:
    """([(σύνολο λέξεων, πλήθος λέξεων, πρόταση)], σύνολο λέξεων του Οίκου),
    χωρίς το «Κεντρικό θέμα»."""
    body = _CENTRAL_THEME.split(body)[0]
    sentences, total = [], 0
    for sentence in _SENTENCE_SPLIT.split(body):
        words = _neutral_words(sentence)
        total += len(words)
        if len(words) >= REPEAT_MIN_WORDS:
            sentences.append((set(words), len(words), sentence.strip()))
    return sentences, total


def _similar(a: set, b: set) -> bool:
    return len(a & b) / len(a | b) >= SIMILAR_SENTENCE


def _entities(sentence: str) -> tuple:
    """Σημεία, ζώδια και αριθμοί Οίκων που ονομάζει μια πρόταση."""
    from validation_aspects import _name_matches
    from validation_structure import _SIGN_ANY, _sign_from_word

    points = frozenset(name for _, _, name in _name_matches(sentence))
    signs = frozenset(
        _sign_from_word(m.group(0)) for m in re.finditer(rf"(?<!\w)(?:{_SIGN_ANY})(?!\w)", sentence, re.IGNORECASE)
    )
    numbers = frozenset(re.findall(r"\d+", sentence))
    return points, signs, numbers


def _same_entities(a: str, b: str) -> bool:
    """v14: «Κυβερνήτης του Οίκου είναι ο Δίας, στον Σκορπιό…» και
    «Κυβερνήτης του Οίκου είναι η Αφροδίτη, στον Αιγόκερω…» έχουν ίδια
    σύνταξη αλλά ΔΙΑΦΟΡΕΤΙΚΟ περιεχόμενο: δεν είναι «η ίδια πρόταση»."""
    return _entities(a) == _entities(b)


def _repeated_text(houses: dict[int, str]):
    """(απορρίψεις, προειδοποιήσεις).

    Απορρίψεις: [(Οίκοι, δείγμα)] -- ομάδες Οίκων που αντιγράφουν ουσιαστικό
    μέρος ο ένας τον άλλον.
    Προειδοποιήσεις: [(Οίκοι, πρόταση)] -- ΜΙΑ ανά επαναλαμβανόμενη πρόταση,
    με όλους τους Οίκους της· για ανάγνωση, όχι κλείδωμα.
    """
    parsed = {n: _house_sentences(body) for n, body in houses.items()}
    numbers = sorted(parsed)
    blocking_pairs = []
    small_repeats = []  # (σύνολο λέξεων, Οίκος a, Οίκος b, πρόταση)
    for i, a in enumerate(numbers):
        for b in numbers[i + 1 :]:
            (sa, total_a), (sb, total_b) = parsed[a], parsed[b]
            matches = []
            for words_a, count_a, text_a in sa:
                match = next(
                    (m for m in sb if _similar(words_a, m[0]) and _same_entities(text_a, m[2])), None
                )
                if match:
                    matches.append((words_a, min(count_a, match[1]), text_a))
            if not matches:
                continue
            shared_words = sum(m[1] for m in matches)
            share = shared_words / max(1, min(total_a, total_b))
            substantial = len(matches) >= MIN_SHARED_SENTENCES or shared_words >= MIN_SHARED_WORDS
            if share >= MAX_SHARED_SHARE and substantial:
                blocking_pairs.append((a, b, matches[0][2]))
            else:
                small_repeats.extend((m[0], a, b, m[2]) for m in matches)

    # Ομαδοποίηση απορρίψεων: αν 1=2 και 2=3, αναφέρεται μία ομάδα {1, 2, 3}.
    groups: list[tuple[set, str]] = []
    for a, b, sample in blocking_pairs:
        hit = [g for g in groups if a in g[0] or b in g[0]]
        merged = {a, b}.union(*(g[0] for g in hit)) if hit else {a, b}
        groups = [g for g in groups if g not in hit] + [(merged, hit[0][1] if hit else sample)]
    blocking = [(sorted(g), sample[:160]) for g, sample in groups]
    blocked = [set(g) for g, _ in blocking]

    # Ομαδοποίηση προειδοποιήσεων: μία ανά (σχεδόν) ίδια πρόταση.
    clusters: list[list] = []  # [σύνολο λέξεων, Οίκοι, πρόταση]
    for words, a, b, sentence in small_repeats:
        if any(a in g and b in g for g in blocked):
            continue  # ήδη μέρος απόρριψης
        cluster = next(
            (c for c in clusters if _similar(words, c[0]) and _same_entities(sentence, c[2])), None
        )
        if cluster is None:
            clusters.append([words, {a, b}, sentence])
        else:
            cluster[1].update((a, b))
    warnings = [(sorted(c[1]), c[2][:160]) for c in clusters]
    return blocking, warnings


# v14.5 (εντολή αναδιατύπωσης v9): μετρήσεις ύφους -- ΔΕΝ κλειδώνουν.
_WEIGHT_LABEL = re.compile(
    r",\s*(?:επίσης\s+|εξίσου\s+|κι\s+αυτ[όή]\s+)?(?:δυνατ[όή]|ήπι[οα])\s*,"
    r"|(?:^|(?<=[.!;]\s))Πιο\s+ήπια,|στο\s+ίδιο\s+ήπιο\s+επίπεδο"
    r"|,\s*(?:a\s+strong\s+one|a\s+gentle\s+one|also\s+(?:strong|gentle))\s*,"
    r"|(?:^|(?<=[.!;]\s))More\s+gently,",
    re.IGNORECASE | re.MULTILINE,
)
_THEME_LINE = re.compile(r"(?:Κεντρικό\s+θέμα|Central\s+theme)\s*:\s*([^\n]+)", re.IGNORECASE)
MAX_ASPECT_HOUSES = 2  # κανόνας 8 της εντολής v9
MAX_THEME_WORDS = 25  # κανόνας 15 της εντολής v9


def _style_warnings(rewrite_text: str) -> list[str]:
    """Όψεις που κατονομάζονται σε πολλούς Οίκους, ετικέτες βαρύτητας σε
    πρόζα, μακριά «Κεντρικά θέματα». Βοηθητικές ενδείξεις προς ανάγνωση."""
    from validation_aspects import _aspect_claims
    from validation_structure import _segments_bounds

    notes = []
    houses_by_pair: dict = {}
    for n, start, end in _segments_bounds(rewrite_text):
        for claim in _aspect_claims(rewrite_text[start:end]):
            houses_by_pair.setdefault(frozenset(claim[:2]), set()).add(n)
    many = sorted(
        ((pair, houses) for pair, houses in houses_by_pair.items() if len(houses) > MAX_ASPECT_HOUSES),
        key=lambda item: (-len(item[1]), sorted(item[0])),
    )
    if many:
        sample = "· ".join(
            f"{'–'.join(sorted(pair))} σε {len(houses)} Οίκους" for pair, houses in many[:4]
        )
        notes.append(
            f"{len(many)} από τις {len(houses_by_pair)} όψεις του εντύπου κατονομάζονται σε περισσότερους από "
            f"{MAX_ASPECT_HOUSES} Οίκους (π.χ. {sample}). Δεν κλειδώνει τη λήψη· κάθε όψη ερμηνεύεται πλήρως "
            "μία φορά και αλλού μεταφέρεται μόνο ό,τι διαφορετικό προσθέτει (κανόνας 8)."
        )
    labels = len(_WEIGHT_LABEL.findall(rewrite_text))
    if labels >= 6:
        notes.append(
            f"{labels} όψεις συνοδεύονται από ετικέτα βαρύτητας («δυνατό», «ήπιο», «πιο ήπια», "
            "«a strong one», «also gentle»). Δεν κλειδώνει τη λήψη· η ιεράρχηση φαίνεται από τη σειρά και την "
            "έκταση, όχι από ετικέτα σε κάθε όψη (κανόνας 22)."
        )
    long_themes = [
        t.strip() for t in _THEME_LINE.findall(rewrite_text) if len(t.split()) > MAX_THEME_WORDS
    ]
    if long_themes:
        notes.append(
            f"{len(long_themes)} «Κεντρικά θέματα» ξεπερνούν τις {MAX_THEME_WORDS} λέξεις (π.χ. "
            f"«{long_themes[0][:120]}»). Δεν κλειδώνει τη λήψη (κανόνας 15)."
        )
    return notes


def _content_problems(chart, source_text: str, rewrite_text: str):
    """(λίγο κείμενο ανά Οίκο, Οίκοι χωρίς «Κεντρικό θέμα», πλανήτες που δεν
    κατονομάζονται στον Οίκο τους, ενότητες χωρίς περιεχόμενο)."""
    source_houses, _ = _document_parts(source_text)
    houses, sections = _document_parts(rewrite_text)
    thin, no_theme, unnamed, empty_sections = [], [], [], []
    for n, body in sorted(houses.items()):
        words = _words(body)
        source_words = _prose_words(source_houses.get(n, ""))
        needed = max(MIN_HOUSE_WORDS, int(source_words * MIN_HOUSE_SHARE))
        if words < needed:
            thin.append((n, words, needed))
        if not _CENTRAL_THEME.search(body):
            no_theme.append(n)
        for point in getattr(chart, "points", []) or []:
            if point.house == n and point.kind in ("planet", "node"):
                if not re.search(_name_pattern(point.name), body, re.IGNORECASE):
                    unnamed.append((n, point.name))
    for section, body in sections.items():
        if section in _TRACKED_SECTIONS and _words(body) < MIN_SECTION_WORDS:
            empty_sections.append((section, _words(body)))
    repeated, repeated_warnings = _repeated_text(houses)
    return thin, no_theme, unnamed, empty_sections, repeated, repeated_warnings


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
            sentence = " ".join(text[left + 1 : right].split())[:220]
            key = (category, sentence)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found


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
    thin_houses: list = field(default_factory=list)  # (Οίκος, λέξεις, απαιτούμενες)
    houses_without_theme: list = field(default_factory=list)
    unnamed_planets: list = field(default_factory=list)  # (Οίκος, σημείο)
    empty_sections: list = field(default_factory=list)  # (ενότητα, λέξεις)
    repeated_text: list = field(default_factory=list)  # ([Οίκοι], δείγμα) -- κλειδώνει
    warnings: list = field(default_factory=list)  # προς ανάγνωση -- ΔΕΝ κλειδώνει
    wrong_sign_claims: list = field(default_factory=list)  # (σημείο, δηλωμένο, σωστό, πλαίσιο)
    # v14: το έντυπο του πελάτη ελέγχεται και για δηλώσεις που δεν υπάρχουν
    # στον χάρτη -- πριν, μια επινοημένη όψη στην αναδιατύπωση περνούσε.
    undeclared_aspects: list = field(default_factory=list)  # (Α, Β, τύπος, απόσπασμα)
    aspect_claim_mismatches: list = field(default_factory=list)  # (όψη, διαφορά, απόσπασμα)
    wrong_ruler_claims: list = field(default_factory=list)  # (Οίκος, δηλωμένος, αναμενόμενοι, πού)
    wrong_data_claims: list = field(default_factory=list)  # (περιγραφή, πλαίσιο)

    def summary(self) -> str:
        if self.ok:
            return (
                "✓ Ο μηχανικός έλεγχος (φίλτρο προφανών παραλείψεων) πέρασε: 12 Οίκοι με δικό τους "
                "κείμενο και «Κεντρικό θέμα», "
                "κάθε πλανήτης κατονομάζεται στον Οίκο του, όλες οι ενότητες της πηγής υπάρχουν με "
                "περιεχόμενο, σωστές τοποθετήσεις και ζώδια, καμία όψη ή κυβερνήτης που δεν υπάρχει στον χάρτη, χωρίς τεχνικά δεδομένα (μοίρες, orb, "
                "βαρύτητες, Παράρτημα). Δεν είναι έγκριση της ερμηνείας: ΔΕΝ ελέγχεται μηχανικά αν η "
                "ερμηνεία αποδίδει πιστά και πλήρως την ελεγμένη ανάλυση — αυτό χρειάζεται τη δική σου "
                "ανάγνωση πριν την παράδοση."
            )
        counts = []
        if self.missing_houses:
            counts.append(f"λείπουν Οίκοι: {', '.join(map(str, self.missing_houses))}")
        if self.missing_source_sections:
            counts.append(
                "λείπουν υποχρεωτικές ενότητες της πηγής: "
                + ", ".join(self.missing_source_sections)
            )
        if self.invented_sections:
            counts.append(
                "προστέθηκαν ενότητες που δεν υπήρχαν στην πηγή: "
                + ", ".join(self.invented_sections)
            )
        if self.thin_houses:
            counts.append(
                "Οίκοι χωρίς επαρκές κείμενο: " + ", ".join(str(n) for n, _, _ in self.thin_houses)
            )
        if self.houses_without_theme:
            counts.append(
                "Οίκοι χωρίς «Κεντρικό θέμα»: " + ", ".join(map(str, self.houses_without_theme))
            )
        if self.unnamed_planets:
            counts.append(f"{len(self.unnamed_planets)} πλανήτες δεν αναφέρονται στον Οίκο τους")
        if self.empty_sections:
            counts.append(
                "ενότητες χωρίς περιεχόμενο: " + ", ".join(s for s, _ in self.empty_sections)
            )
        if self.repeated_text:
            counts.append(f"{len(self.repeated_text)} επαναλήψεις ίδιου κειμένου σε διαφορετικούς Οίκους")
        if self.wrong_house_claims:
            counts.append(f"{len(self.wrong_house_claims)} λανθασμένες τοποθετήσεις")
        if self.wrong_sign_claims:
            counts.append(f"{len(self.wrong_sign_claims)} λανθασμένες δηλώσεις ζωδίου")
        if self.undeclared_aspects:
            counts.append(f"{len(self.undeclared_aspects)} όψεις που δεν υπάρχουν στον ελεγμένο χάρτη")
        if self.aspect_claim_mismatches:
            counts.append(f"{len(self.aspect_claim_mismatches)} όψεις με λάθος τύπο")
        if self.wrong_ruler_claims:
            counts.append(f"{len(self.wrong_ruler_claims)} λανθασμένες δηλώσεις κυβερνήτη")
        if self.wrong_data_claims:
            counts.append(f"{len(self.wrong_data_claims)} λανθασμένες δηλώσεις κίνησης ή ζωδίου ακμής")
        if self.unauthorized_personal_claims:
            counts.append(
                f"{len(self.unauthorized_personal_claims)} μη εξουσιοδοτημένες προσωπικές αναφορές"
            )
        if self.technical_data:
            counts.append(
                f"{len(self.technical_data)} σημεία με τεχνικά αστρολογικά δεδομένα που δεν πρέπει να βλέπει ο πελάτης"
            )
        return "Η αναδιατύπωση απορρίφθηκε: " + "· ".join(counts) + "."

    def details_lines(self) -> list[str]:
        lines = []
        for n in self.missing_houses:
            lines.append(f"Δεν εντοπίστηκε ο {n}ος Οίκος.")
        for s in self.missing_source_sections:
            lines.append(f"Η πηγή περιέχει την ενότητα «{s}», αλλά η αναδιατύπωση την παρέλειψε.")
        for s in self.invented_sections:
            lines.append(
                f"Η αναδιατύπωση πρόσθεσε την ενότητα «{s}», παρότι δεν υπάρχει στην ελεγμένη πηγή."
            )
        for n, words, needed in self.thin_houses:
            lines.append(
                f"{n}ος Οίκος: μόνο {words} λέξεις κειμένου (χρειάζονται τουλάχιστον {needed}, "
                "ανάλογα με την έκταση του Οίκου στην ελεγμένη ανάλυση)."
            )
        for n in self.houses_without_theme:
            lines.append(f"{n}ος Οίκος: λείπει η πρόταση «Κεντρικό θέμα:» (κανόνας 15).")
        for n, point_name in self.unnamed_planets:
            lines.append(
                f"{n}ος Οίκος: δεν αναφέρεται καθόλου το σημείο {point_name}, που βρίσκεται σε "
                "αυτόν τον Οίκο (κανόνας 7) — πιθανή απώλεια της ερμηνείας του."
            )
        for section, words in self.empty_sections:
            lines.append(
                f"Η ενότητα «{section}» έχει μόνο {words} λέξεις (χρειάζονται τουλάχιστον {MIN_SECTION_WORDS})."
            )
        for group, sample in self.repeated_text:
            where = ", ".join(f"{n}ος" for n in group)
            lines.append(
                f"Ουσιαστικό μέρος του κειμένου επαναλαμβάνεται σε διαφορετικούς Οίκους ({where}), "
                f"π.χ. «{sample}» — κάθε Οίκος χρειάζεται τη δική του ερμηνεία (κανόνας 9)."
            )
        for point_name, claimed, expected, snippet in self.wrong_house_claims:
            lines.append(
                f"Λανθασμένη τοποθέτηση — {point_name}: δηλώνεται στον {claimed}ο αντί στον {expected}ο Οίκο. Σημείο: {snippet}"
            )
        for a, b, t, snip in self.undeclared_aspects:
            lines.append(
                f"Αναφορά σε όψη που δεν υπάρχει στον χάρτη — {a}–{b} ({t}). Το πρόγραμμα διάβασε: "
                f"«{t}» ανάμεσα σε {a} και {b}· στα ελεγμένα δεδομένα δεν υπάρχει καμία όψη για αυτό το ζεύγος. "
                f"Σημείο: «{snip}»"
            )
        for a, diff, snip in self.aspect_claim_mismatches:
            lines.append(
                f"Λάθος δήλωση όψης — {a.first}–{a.second}: {diff} (ελεγμένα: {a.aspect}). Σημείο: «{snip}»"
            )
        for house_n, claimed, expected, where in self.wrong_ruler_claims:
            lines.append(
                f"{house_n}ος Οίκος: το {where} δηλώνει κυβερνήτη {claimed}, ενώ από το ζώδιο της ακμής είναι {expected}."
            )
        for description, context in self.wrong_data_claims:
            lines.append(f"{description}. Σημείο: {context}")
        for category, snippet in self.unauthorized_personal_claims:
            lines.append(f"Μη δηλωμένο προσωπικό στοιχείο ({category}): «{snippet}»")
        shown = self.technical_data[:40]
        for category, sentence in shown:
            lines.append(
                f"Τεχνικό δεδομένο ({category}) — να αφαιρεθεί από το έντυπο του πελάτη: «{sentence}»"
            )
        if len(self.technical_data) > len(shown):
            lines.append(
                f"…και {len(self.technical_data) - len(shown)} ακόμη σημεία με τεχνικά δεδομένα "
                "(συνήθως γραμμές πίνακα/Παραρτήματος όψεων)."
            )
        for point_name, claimed, expected, snippet in self.wrong_sign_claims:
            lines.append(
                f"Λανθασμένο ζώδιο — {point_name}: γράφεται {claimed} αντί για {expected}. Σημείο: {snippet}"
            )
        return lines


def validate_rewrite(
    chart, source_text: str, rewrite_text: str, personal: dict | None = None
) -> RewriteValidationResult:
    """Έλεγχος του τελικού εντύπου πελάτη.

    Η πηγή (ελεγμένο τεχνικό Word) περιέχει τα τεχνικά δεδομένα και το
    Παράρτημα· η αναδιατύπωση ΔΕΝ πρέπει να τα περιέχει. Ελέγχεται ότι:
    υπάρχουν οι 12 Οίκοι και οι ερμηνευτικές ενότητες της πηγής, δεν
    προστέθηκαν νέες ενότητες, δεν υπάρχουν λάθος τοποθετήσεις πλανητών ή
    μη δηλωμένα προσωπικά στοιχεία, δεν εμφανίζονται μοίρες/orb/βαρύτητες/
    Παράρτημα, κάθε Οίκος και ενότητα έχει ουσιαστικό κείμενο, κάθε Οίκος
    κλείνει με «Κεντρικό θέμα:» και κάθε πλανήτης κατονομάζεται στον Οίκο του.
    Η ερμηνευτική πιστότητα ΔΕΝ ελέγχεται μηχανικά.
    """
    source_text = _normalize_prime_marks(source_text)
    rewrite_text = _normalize_prime_marks(rewrite_text)
    missing_houses = [
        n
        for n in range(1, 13)
        if not (
            _HOUSE_PATTERNS[n - 1].search(rewrite_text)
            or _HOUSE_PATTERNS_ALT[n - 1].search(rewrite_text)
            or _HOUSE_WORD_PATTERNS[n - 1].search(rewrite_text)
        )
    ]
    # Το Παράρτημα δεν μεταφέρεται στο έντυπο πελάτη -- ελέγχεται ξεχωριστά
    # ως τεχνικό δεδομένο, όχι ως ενότητα που «λείπει».
    tracked_sections = [s for s in _SECTION_PATTERNS if not s.startswith("Παράρτημα")]
    source_has = {s: _has_section(source_text, s) for s in tracked_sections}
    rewrite_has = {s: _has_section(rewrite_text, s) for s in tracked_sections}
    missing_source_sections = [s for s in tracked_sections if source_has[s] and not rewrite_has[s]]
    invented_sections = [s for s in tracked_sections if not source_has[s] and rewrite_has[s]]
    wrong_house_claims = _location_claim_errors(chart, rewrite_text)
    unauthorized = _unauthorized_personal_claims(personal, rewrite_text)
    technical = _client_technical_data(rewrite_text)
    wrong_signs = _sign_claim_errors(chart, rewrite_text)
    undeclared_aspects, aspect_mismatches = _aspect_claim_problems(chart, rewrite_text)
    wrong_rulers = _ruler_role_errors(chart, rewrite_text)
    wrong_data = _data_claim_errors(chart, rewrite_text)
    thin, no_theme, unnamed, empty_sections, repeated, repeated_warnings = _content_problems(
        chart, source_text, rewrite_text
    )
    warnings = [
        f"Η ίδια πρόταση εμφανίζεται σε {len(group)} Οίκους ({', '.join(f'{n}ο' for n in group)}): "
        f"«{sample}». Δεν κλειδώνει τη λήψη· έλεγξε αν η επανάληψη είναι σκόπιμη (κανόνας 9)."
        for group, sample in repeated_warnings
    ]
    warnings = _style_warnings(rewrite_text) + warnings

    ok = not (
        repeated
        or
        thin
        or no_theme
        or unnamed
        or empty_sections
        or
        missing_houses
        or missing_source_sections
        or invented_sections
        or wrong_house_claims
        or unauthorized
        or technical
        or wrong_signs
        or undeclared_aspects
        or aspect_mismatches
        or wrong_rulers
        or wrong_data
    )
    return RewriteValidationResult(
        ok,
        missing_houses,
        missing_source_sections,
        invented_sections,
        wrong_house_claims,
        unauthorized,
        technical,
        wrong_sign_claims=wrong_signs,
        thin_houses=thin,
        houses_without_theme=no_theme,
        unnamed_planets=unnamed,
        empty_sections=empty_sections,
        repeated_text=repeated,
        warnings=warnings,
        undeclared_aspects=undeclared_aspects,
        aspect_claim_mismatches=aspect_mismatches,
        wrong_ruler_claims=wrong_rulers,
        wrong_data_claims=wrong_data,
    )
