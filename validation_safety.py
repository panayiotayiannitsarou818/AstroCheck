"""v18: έλεγχος ασφαλούς γλώσσας και ουσιαστικού περιεχομένου.

Οι Οδηγίες και η Δεσμευτική Εντολή απαγορεύουν διαγνώσεις υγείας, βέβαιες
προβλέψεις και απόλυτα επαγγελματικά συμπεράσματα. Μέχρι τη v17.1 αυτό ήταν
μόνο οδηγία προς το μοντέλο· τώρα ελέγχεται και μηχανικά, ώστε ένα κείμενο
με τέτοιες φράσεις να ΜΗΝ περνά τον έλεγχο.

Ο έλεγχος δουλεύει ανά πρόταση:
- Υγεία: κλινικός όρος σε πρόταση ΧΩΡΙΣ άρνηση («όχι διάγνωση» περνά,
  «έχεις κατάθλιψη» κόβεται). Ο Καρκίνος ως ζώδιο ΔΕΝ είναι κλινικός όρος.
- Βέβαιη πρόβλεψη: λέξη βεβαιότητας μαζί με μέλλοντα, ή μελλοντικό
  αποτέλεσμα ζωής (θα αποτύχει, θα χωρίσεις, θα πετύχεις...) χωρίς
  πιθανολογική διατύπωση, ή μοιρολατρία («είσαι προορισμένη»).
- Επάγγελμα: απόλυτη οδηγία ή αποκλεισμός («πρέπει να γίνεις»,
  «το σωστό επάγγελμα για σένα είναι», «δεν είσαι κατάλληλη για»).
"""

from __future__ import annotations

import re

CAT_HEALTH = "διάγνωση ή ιατρικός ισχυρισμός"
CAT_CERTAIN = "βέβαιη πρόβλεψη"
CAT_FATE = "μοιρολατρική διατύπωση"
CAT_CAREER = "απόλυτο επαγγελματικό συμπέρασμα"

_F = re.IGNORECASE | re.UNICODE

_SENTENCE_SPLIT = re.compile(r"(?<=[.!;?·])\s+|\n+")

_NEGATION = re.compile(
    r"(?<!\w)(?:όχι|δεν|μη|μην|ούτε|ουδέποτε|not|no|never|isn['’]t|doesn['’]t|don['’]t|without)(?!\w)", _F
)
_HEDGE = re.compile(
    r"(?<!\w)(?:μπορεί|ίσως|ενδέχεται|ενδεχομένως|πιθαν\w*|τείνει|τείνεις|αν|εάν|εφόσον|όταν|"
    r"may|might|could|perhaps|possibly|likely|if|when|tend\w*)(?!\w)",
    _F,
)

# --- Υγεία ---------------------------------------------------------------
_CLINICAL_CORE = (
    r"(?:"
    r"κατάθλιψ\w*|καταθλιπτικ\w*|αντικαταθλιπτικ\w*|διπολικ\w*|σχιζοφρέν\w*|ψύχωσ\w*|ψυχωτικ\w*|"
    r"ΔΕΠΥ|ADHD|αυτισμ\w*|αυτιστικ\w*|ψυχιατρ\w*|ψυχοφάρμακ\w*|φαρμακευτικ\w+\s+αγωγ\w*|"
    r"(?:ψυχικ\w+|αγχώδ\w+|διατροφικ\w+)\s+διαταραχ\w*|διαταραχ\w*\s+(?:άγχους|πανικού|προσωπικότητας|"
    r"διατροφής|ύπνου|διάθεσης)|νευρικ\w+\s+ανορεξ\w*|βουλιμ\w*|ναρκισσιστικ\w+\s+διαταραχ\w*|"
    r"διάγνωσ[ηεισ]\w*|διαγιγνώσκ\w*|διαγνώστηκ\w*|ασθένει\w*|νόσο\w*|νόσος|"
    r"καρκίνο\w*\s+(?:του|της|στο|στη|στον|στην)\s+(?:μαστού|πνεύμονα|δέρματος|παχέος|προστάτη|μήτρας|"
    r"στομάχου|εντέρου|αίματος)|καρκινοπαθ\w*|αρρωστήσ\w*|διαβήτ\w*|υπέρτασ\w*|στειρότητ\w*|"
    r"depression|depressive|antidepressant\w*|bipolar|schizophren\w*|psychos[ie]s|psychotic|"
    r"autis\w*|psychiatr\w*|disorder\w*|diagnos(?:is|es|ed|e)|disease\w*|illness\w*|tumou?r\w*|diabetes|"
    r"infertil\w*|medication"
    r")"
)
_CLINICAL = re.compile(r"(?<!\w)" + _CLINICAL_CORE + r"(?!\w)", _F)
# Πρόταση που ΣΥΣΤΗΝΕΙ επαγγελματία βοήθεια χωρίς να διαγιγνώσκει είναι θεμιτή.
_REFERRAL = re.compile(
    r"(?:επαγγελματία\s+(?:ψυχικής|σωματικής)|κατάλληλο\s+επαγγελματία|qualified\s+professional|"
    r"health\s+professional|(?:μίλησε|μιλήσεις|συζήτησ\w*|απευθύν\w*|συμβουλ\w*)\s+(?:με|σε|έναν?)\s+"
    r"(?:\w+\s+)?(?:γιατρ\w*|ειδικ\w*|επαγγελματ\w*|ψυχολόγ\w*)|"
    r"(?:talk|speak)\s+(?:to|with)\s+(?:a\s+)?(?:doctor|professional|specialist|therapist))",
    _F,
)
_DIRECT_HEALTH = re.compile(
    r"(?<!\w)(?:έχεις|πάσχεις(?:\s+από)?|υποφέρεις(?:\s+από)?|θα\s+(?:πάθεις|εμφανίσεις|αναπτύξεις)|"
    r"χρειάζεσαι|you\s+(?:have|suffer\s+from|will\s+develop|need))\s+(?:[^\W\d_]+\s+){0,3}"
    + _CLINICAL_CORE + r"(?!\w)|χρειάζεσαι\s+(?:ψυχιατρικ\w+|φαρμακευτικ\w+)\s+\w+",
    _F,
)


# --- Βέβαιες προβλέψεις ----------------------------------------------------
_CERTAINTY = re.compile(
    r"(?<!\w)(?:σίγουρα|σιγουρα|οπωσδήποτε|αναπόφευκτα|αναπόφευκτ\w+|αναμφίβολα|εγγυημένα|"
    r"χωρίς\s+(?:καμία\s+)?αμφιβολία|είναι\s+(?:βέβαιο|σίγουρο)\s+ότι|100\s?%|"
    r"definitely|certainly|surely|inevitabl\w*|guaranteed|without\s+(?:a\s+|any\s+)?doubt|for\s+sure)(?!\w)",
    _F,
)
_FUTURE = re.compile(r"(?<!\w)(?:θα|will|going\s+to)(?!\w)", _F)
_LIFE_OUTCOME = re.compile(
    r"(?<!\w)(?:θα\s+(?:\w+\s+)?(?:αποτύχ\w*|χωρίσ\w*|πεθάν\w*|αρρωστήσ\w*|χρεοκοπήσ\w*|καταστραφ\w*|"
    r"πετύχ\w*|πλουτίσ\w*|παντρευτ\w*|χάσ\w*|απολυθ\w*|μείνεις\s+μόν\w+|βρεις\s+τον\s+έρωτα|"
    r"κάνεις\s+παιδιά|γίνεις\s+διάσημ\w*)|"
    r"will\s+(?:\w+\s+)?(?:fail|divorce|die|get\s+sick|go\s+bankrupt|succeed|get\s+rich|marry|"
    r"lose|be\s+fired|end\s+up\s+alone|become\s+famous))(?!\w)",
    _F,
)
_FATE = re.compile(
    r"(?<!\w)(?:προορισμέν\w+|είναι\s+γραφτό|ήταν\s+γραφτό|είναι\s+μοιραίο|η\s+μοίρα\s+σου\s+είναι|"
    r"destined|fated|it\s+is\s+written|your\s+fate\s+is)(?!\w)",
    _F,
)

# --- Απόλυτα επαγγελματικά συμπεράσματα -----------------------------------
_CAREER = re.compile(
    r"(?<!\w)(?:πρέπει\s+να\s+(?:γίνεις|σπουδάσεις|ακολουθήσεις|δουλέψεις\s+ως|εργαστείς\s+ως)|"
    r"(?:το|η)\s+(?:σωστ|ιδανικ|μόν|κατάλληλ)\w+\s+(?:επάγγελμα|καριέρα|δουλειά|επαγγελματική\s+επιλογή)\s+"
    r"(?:για\s+σένα|σου)|"
    r"είσαι\s+(?:γεννημέν|φτιαγμέν)\w+\s+(?:για|να)|"
    r"δεν\s+(?:είσαι|κάνεις)\s+(?:κατάλληλ\w+\s+|φτιαγμέν\w+\s+)?για\s+(?:\w+\s+){0,3}(?:επάγγελμα|καριέρα|δουλειά|ρόλο|θέση|σπουδές)|"
    r"ακατάλληλ\w+\s+για|μη(?:ν)?\s+(?:γίνεις|σπουδάσεις|ακολουθήσεις)|"
    r"you\s+(?:must|should)\s+(?:become|study|pursue)|the\s+(?:right|only|ideal)\s+(?:career|job|profession)\s+for\s+you|"
    r"you\s+are\s+(?:born|made)\s+(?:to|for)|you\s+are\s+not\s+(?:suited|cut\s+out|made)\s+for|unsuited\s+for)(?!\w)",
    _F,
)


def _sentences(text: str):
    for raw in _SENTENCE_SPLIT.split(text or ""):
        s = " ".join(raw.split())
        if len(s) >= 4:
            yield s


def unsafe_claims(text: str) -> list[tuple[str, str]]:
    """(κατηγορία, πρόταση) για κάθε μη ασφαλή διατύπωση. Κλειδώνει την έγκριση."""
    found: list[tuple[str, str]] = []
    seen = set()

    def add(cat, sentence):
        key = (cat, sentence[:220])
        if key not in seen:
            seen.add(key)
            found.append(key)

    for s in _sentences(text):
        negated = bool(_NEGATION.search(s))
        hedged = bool(_HEDGE.search(s))
        # Υγεία: άμεση διάγνωση κόβεται πάντα· κλινικός όρος κόβεται αν δεν
        # υπάρχει άρνηση ή σύσταση για επαγγελματία.
        if _CLINICAL.search(s):
            if _DIRECT_HEALTH.search(s):
                add(CAT_HEALTH, s)
            elif not negated and not _REFERRAL.search(s):
                add(CAT_HEALTH, s)
        if _CERTAINTY.search(s) and _FUTURE.search(s) and not negated:
            add(CAT_CERTAIN, s)
        elif _LIFE_OUTCOME.search(s) and not hedged:
            add(CAT_CERTAIN, s)
        if _FATE.search(s) and not negated:
            add(CAT_FATE, s)
        if _CAREER.search(s):
            add(CAT_CAREER, s)
    return found


def unsafe_claim_lines(items) -> list[str]:
    return [
        f"Μη ασφαλής διατύπωση ({cat}) — να ξαναγραφτεί πιθανολογικά, ως συμβολική τάση και όχι ως "
        f"γεγονός, διάγνωση ή βέβαιη έκβαση: «{sentence}»"
        for cat, sentence in items
    ]


# --- Ουσιαστικό περιεχόμενο τεχνικής ανάλυσης -------------------------------

SUMMARY_TEXT_LABELS = (
    "Βασική δύναμη",
    "Βασική πρόκληση",
    "Τελικό συμπέρασμα",
    "Key strength",
    "Key challenge",
    "Final conclusion",
)
MIN_SUMMARY_WORDS = 6
# Οι παλιές δοκιμές κανόνων δεδομένων χρησιμοποιούν σκόπιμα «σκελετικά» κείμενα
# χωρίς ερμηνεία· το conftest.py απενεργοποιεί ΜΟΝΟ για αυτές τον έλεγχο ουσίας.
# Στην εφαρμογή είναι πάντα ενεργός.
SUBSTANCE_CHECK_ENABLED = True
MIN_HOUSE_PROSE_WORDS = 120

_PLACEHOLDER = re.compile(
    r"^(?:κείμενο|text|—|-|–|\.{2,}|…|tbd|todo|xxx+|lorem\b.*|\[.*\]|<.*>|συμπληρώνεται|"
    r"συμπλήρωση|placeholder|n/?a|κενό|κενη|κενή)\W*$",
    _F,
)
_LABEL_LINE = re.compile(
    r"^\s*(" + "|".join(re.escape(lbl) for lbl in SUMMARY_TEXT_LABELS) + r")\s*[:\-–—]\s*(.*)$",
    _F | re.MULTILINE,
)
_ASPECT_ROW = re.compile(r"\borb\b|\|", _F)
_ANY_LABEL = re.compile(r"^\s*[\wΆ-ώ ]{2,40}:\s*\S{0,40}\s*$")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _prose_words(segment: str) -> int:
    total = 0
    lines = segment.splitlines()
    for i, line in enumerate(lines):
        t = line.strip()
        if i == 0 or not t:
            continue  # επικεφαλίδα Οίκου
        if _ASPECT_ROW.search(t) or _LABEL_LINE.match(t) or _ANY_LABEL.match(t):
            continue
        words = _WORD.findall(t)
        if len(words) < 8:
            continue  # υπότιτλος, όχι ερμηνευτικό κείμενο
        total += len(words)
    return total


def thin_analysis_content(segments: dict) -> list[tuple[int, str]]:
    """(Οίκος, περιγραφή) για Οίκους με κενές ετικέτες ή ελάχιστη ερμηνεία."""
    problems: list[tuple[int, str]] = []
    if not SUBSTANCE_CHECK_ENABLED:
        return problems
    for n in range(1, 13):
        seg = segments.get(n)
        if not seg:
            continue
        for m in _LABEL_LINE.finditer(seg):
            label, value = m.group(1), m.group(2).strip()
            words = len(_WORD.findall(value))
            if not value or _PLACEHOLDER.match(value) or words < MIN_SUMMARY_WORDS:
                problems.append(
                    (n, f"η γραμμή «{label}:» δεν έχει ουσιαστικό περιεχόμενο («{value[:60]}»· "
                        f"χρειάζεται πλήρης πρόταση, τουλάχιστον {MIN_SUMMARY_WORDS} λέξεις)")
                )
        words = _prose_words(seg)
        if words < MIN_HOUSE_PROSE_WORDS:
            problems.append(
                (n, f"μόνο {words} λέξεις ερμηνευτικού κειμένου (χρειάζονται τουλάχιστον "
                    f"{MIN_HOUSE_PROSE_WORDS}, εκτός πινάκων, όψεων και ετικετών)")
            )
    return problems


# --- v19: επανάληψη ίδιου κειμένου ανάμεσα σε Οίκους της τεχνικής ανάλυσης ---


def _interpretive_text(segment: str) -> str:
    out = []
    for i, line in enumerate(segment.splitlines()):
        t = line.strip()
        if i == 0 or not t or _ASPECT_ROW.search(t) or _LABEL_LINE.match(t) or _ANY_LABEL.match(t):
            continue
        out.append(t)
    return "\n".join(out)


def repeated_analysis_text(segments: dict) -> list:
    """[(Οίκοι, δείγμα)]: Οίκοι που επαναλαμβάνουν ουσιαστικό μέρος του ίδιου
    γενικόλογου κειμένου. Μεμονωμένες κοινές προτάσεις (π.χ. η ίδια όψη
    ερμηνευμένη σε δύο Οίκους) ΔΕΝ κλειδώνουν."""
    if not SUBSTANCE_CHECK_ENABLED:
        return []
    from validation_rewrite import _repeated_text

    blocking, _ = _repeated_text({n: _interpretive_text(s) for n, s in segments.items() if s})
    return blocking
