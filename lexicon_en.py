"""Αγγλικό λεξιλόγιο του AstroCheck: ΕΝΑ σημείο αλήθειας για τους αγγλικούς όρους.

Χρησιμοποιείται από δύο πλευρές, ώστε να μην αποκλίνουν ποτέ:
  1. prompts.py -- όταν η γλώσσα είναι «Αγγλικά», η εντολή δίνει στο μοντέλο
     ΑΚΡΙΒΩΣ αυτούς τους όρους (ονόματα, όψεις, κατηγορίες βαρύτητας, τίτλους).
  2. validation_patterns.py -- ο validator αναγνωρίζει τους ίδιους όρους.

Τα εσωτερικά δεδομένα (Chart, Aspect) παραμένουν στα ελληνικά. Εδώ υπάρχει
μόνο η αντιστοίχιση «ελληνικό κανονικό όνομα → αγγλικός όρος» και τα
αντίστοιχα regex.
"""

from __future__ import annotations

import re

# --- Σημεία του χάρτη -------------------------------------------------------
POINT_NAMES = {
    "Ήλιος": "Sun",
    "Σελήνη": "Moon",
    "Ερμής": "Mercury",
    "Αφροδίτη": "Venus",
    "Άρης": "Mars",
    "Δίας": "Jupiter",
    "Κρόνος": "Saturn",
    "Ουρανός": "Uranus",
    "Ποσειδώνας": "Neptune",
    "Πλούτωνας": "Pluto",
    "Βόρειος Δεσμός": "North Node",
    "Νότιος Δεσμός": "South Node",
    "Χείρωνας": "Chiron",
    "Ωροσκόπος": "Ascendant",
    "Μεσουράνημα": "Midheaven",
}

NAME_REGEX = {
    "Ήλιος": r"\bSun\b",
    "Σελήνη": r"\bMoon\b",
    "Ερμής": r"\bMercury\b",
    "Αφροδίτη": r"\bVenus\b",
    "Άρης": r"\bMars\b",
    "Δίας": r"\bJupiter\b",
    "Κρόνος": r"\bSaturn\b",
    "Ουρανός": r"\bUranus\b",
    "Ποσειδώνας": r"\bNeptune\b",
    "Πλούτωνας": r"\bPluto\b",
    "Βόρειος Δεσμός": r"\bNorth\s+Node\b",
    "Νότιος Δεσμός": r"\bSouth\s+Node\b",
    "Χείρωνας": r"\bChiron\b",
    "Ωροσκόπος": r"\b(?:Ascendant|ASC)\b",
    "Μεσουράνημα": r"\b(?:Midheaven|MC)\b",
}

# --- Ζώδια ------------------------------------------------------------------
SIGN_NAMES = {
    "Κριός": "Aries",
    "Ταύρος": "Taurus",
    "Δίδυμοι": "Gemini",
    "Καρκίνος": "Cancer",
    "Λέων": "Leo",
    "Παρθένος": "Virgo",
    "Ζυγός": "Libra",
    "Σκορπιός": "Scorpio",
    "Τοξότης": "Sagittarius",
    "Αιγόκερως": "Capricorn",
    "Υδροχόος": "Aquarius",
    "Ιχθύες": "Pisces",
}

# --- Όψεις ------------------------------------------------------------------
ASPECT_NAMES = {
    "Σύνοδος": "Conjunction",
    "Εξάγωνο": "Sextile",
    "Τετράγωνο": "Square",
    "Τρίγωνο": "Trine",
    "Αντίθεση": "Opposition",
    "Χιαστί όψη 150°": "Quincunx 150°",
}

ASPECT_REGEX = {
    "Σύνοδος": r"\bconjunct(?:ions?|s)?\b",
    "Εξάγωνο": r"\bsextiles?\b",
    "Τετράγωνο": r"\bsquares?\b",
    "Τρίγωνο": r"\btrines?\b",
    "Αντίθεση": r"\boppos(?:itions?|es|ed|ing)\b",
    "Χιαστί όψη 150°": r"\b(?:quincunx(?:es)?|inconjuncts?)\b(?:\s+150°)?",
}

# --- Κατηγορίες βαρύτητας ---------------------------------------------------
WEIGHT_NAMES = {
    "Στενή/ισχυρή": "Tight/strong",
    "Κανονική": "Standard",
    "Πλατιά αλλά έγκυρη": "Wide but valid",
    "Πολύ πλατιά/δευτερεύουσα": "Very wide/secondary",
}

WEIGHT_REGEX = {
    "Στενή/ισχυρή": r"\btight\s*/\s*strong\b",
    "Κανονική": r"\bstandard\b",
    "Πλατιά αλλά έγκυρη": r"\bwide\s+but\s+valid\b",
    "Πολύ πλατιά/δευτερεύουσα": r"\bvery\s+wide\s*/\s*secondary\b",
}

# --- Οίκοι ------------------------------------------------------------------
HOUSE_WORDS = [
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
]


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def house_heading(n: int) -> str:
    return f"{ordinal(n)} House"


ORDINAL_SUFFIX = r"(?:st|nd|rd|th)"

# --- Ενότητες ---------------------------------------------------------------
SECTION_TITLES = {
    "Τελική συνθετική εικόνα": "Final synthesis",
    "Συμβολική κατεύθυνση εξέλιξης": "Symbolic direction of growth",
    "Προτάσεις προσωπικής ανάπτυξης": "Suggestions for personal growth",
    "Παράρτημα επιβεβαιωμένων όψεων": "Appendix of confirmed aspects",
}

# Ο αρχικός (δεσμευτικός) αγγλικός τίτλος -- αναγνωρίζεται οπουδήποτε.
SECTION_REGEX = {
    "Τελική συνθετική εικόνα": r"Final\s+synthesis|Final\s+synthetic\s+(?:picture|overview)",
    "Συμβολική κατεύθυνση εξέλιξης": r"Symbolic\s+direction\s+of\s+(?:growth|evolution|development)",
    "Προτάσεις προσωπικής ανάπτυξης": r"Suggestions\s+for\s+personal\s+(?:growth|development)"
    r"|Personal\s+(?:growth|development)\s+suggestions",
    "Παράρτημα επιβεβαιωμένων όψεων": r"Appendix[^\r\n]{0,90}confirmed[^\r\n]{0,40}aspects",
}

# Ισοδύναμοι τίτλοι -- γίνονται δεκτοί ΜΟΝΟ ως τίτλος (ξεχωριστή γραμμή).
SECTION_SYNONYMS = {
    "Τελική συνθετική εικόνα": r"(?:Final|Overall)\s+synthesis|Overall\s+picture"
    r"|Synthesis\s+of\s+the\s+(?:whole\s+)?chart|Final\s+(?:overview|picture)",
    "Συμβολική κατεύθυνση εξέλιξης": r"(?:Symbolic\s+)?direction\s+of\s+(?:growth|evolution|development)"
    r"|(?:Symbolic\s+)?evolutionary\s+direction|(?:The\s+)?(?:Lunar\s+)?Nod(?:es|al\s+axis)"
    r"|(?:The\s+)?axis\s+of\s+the\s+(?:Lunar\s+)?Nodes|North\s*(?:and|/|–|-)\s*South\s+Nodes?",
    "Προτάσεις προσωπικής ανάπτυξης": r"(?:Practical\s+)?(?:Suggestions|Recommendations)(?:\s+for)?"
    r"(?:\s+(?:personal|practical))?(?:\s+(?:and\s+)?(?:growth|development|support|self-awareness|evolution))+",
    "Παράρτημα επιβεβαιωμένων όψεων": r"(?:Technical\s+)?Appendix(?:\s+[^\r\n]{0,60})?"
    r"|Table\s+of\s+(?:confirmed\s+)?aspects|(?:Confirmed\s+)?aspects?\s+table|Confirmed\s+aspects",
}

# --- Κυβερνήτες και πλαίσιο σύνοψης -------------------------------------------
RULER_INTRO_REGEX = [
    r"\b(?:main|modern|primary)(?:\s*\(\s*modern\s*\))?(?:\s*/\s*(?:main|modern|primary))?"
    r"\s+ruler(?:\s+of\s+this\s+house)?\s+is\s+(?:the\s+)?(\S+)",
    r"\btraditional\s+ruler(?:\s+of\s+this\s+house)?\s+is\s+(?:the\s+)?(\S+)",
]

SUMMARY_LABELS = ("Key strength", "Key challenge", "Ruler", "Final conclusion")

# --- Δηλώσεις τοποθέτησης σε Οίκο --------------------------------------------
# Μόνο ρητά ρήματα θέσης ακολουθούμενα ΑΜΕΣΩΣ από «(the) Nth House», ώστε να
# μη μετρά ως θέση το «Mars is the ruler of the 7th House».
PLACEMENT_VERBS = (
    r"(?:\bis\s+(?:placed\s+|located\s+|found\s+|positioned\s+)?in|\blies\s+in|\bsits\s+in"
    r"|\bfalls\s+in|\bresides\s+in|\boccupies|\bplaced\s+in|\blocated\s+in|\bPosition\s*:)"
)

THEME_HOUSES = {
    1: r"identity|self-presentation|personal\s+presence",
    2: r"personal\s+(?:values|resources)|(?<!shared )resources|(?<!shared )finances|self-worth",
    3: r"communication|learning",
    4: r"family|roots|home",
    5: r"creativity|children|joy|romance",
    6: r"daily\s+work|routines?|health",
    7: r"relationships|marriage|partnerships?",
    8: r"shared\s+(?:resources|finances)|trust|transformation",
    9: r"meaning|higher\s+education|philosophy",
    10: r"career|public\s+(?:life|path)|professional\s+path",
    11: r"visions|communit|groups|friends",
    12: r"inner\s+world|behind\s+the\s+scenes|unconscious",
}

# Φράσεις στο κενό «σημείο … in <ζώδιο>» που δείχνουν ότι το ζώδιο ΔΕΝ είναι
# η θέση του σημείου (Θεωρία Μοιρών, κυβέρνηση, ακμή, αντίθετο ζώδιο κ.λπ.).
SIGN_NOT_PLACEMENT = (
    r"degree|correspond|tone|colou?r|rul|cusp|span|extend|from|until|\bto\b|opposite|toward"
    r"|intercept|\bor\b|near|axis|part\s+of|continu"
)

# --- Έντυπο πελάτη -----------------------------------------------------------
# Το έντυπο πελάτη ΔΕΝ κλείνει με πρόταση για μαθηματικό έλεγχο (κανόνας 19).
# Αν εμφανιστεί τέτοια πρόταση, ο validator τη σημειώνει για αφαίρεση.
CLIENT_CHECK_SENTENCE_REGEX = (
    r"based\s+on\s+a\s+(?:full\s+|complete\s+)?mathematical\s+(?:check|verification)"
    r"|technical\s+details\s+are\s+available"
)

CLIENT_WEIGHT_REGEX = r"Tight\s*/\s*strong|Wide\s+but\s+valid|Very\s+wide\s*/\s*secondary"
CLIENT_APPENDIX_REGEX = (
    r"^\s*(?:Technical\s+)?Appendix\b|Appendix[^\r\n]{0,90}confirmed[^\r\n]{0,40}aspects"
)
CLIENT_SOURCE_REGEX = (
    r"Astrodienst\s+table|Mathematical\s+derivation\s+from\s+the\s+(?:[\w/ ]{0,30})axis"
)

# --- Ανίχνευση γλώσσας κειμένου ------------------------------------------------
_GREEK = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")
_LATIN = re.compile(r"[A-Za-z]")


def looks_english(text: str) -> bool:
    """True όταν το κείμενο είναι κυρίως λατινικοί χαρακτήρες (αγγλική ανάλυση)."""
    greek = len(_GREEK.findall(text or ""))
    latin = len(_LATIN.findall(text or ""))
    return latin > 0 and latin > 3 * greek


def en(greek_name: str) -> str:
    """Αγγλικός όρος για οποιοδήποτε ελληνικό κανονικό όνομα (σημείο, ζώδιο,
    όψη, βαρύτητα). Αν δεν υπάρχει αντιστοίχιση, επιστρέφει το ίδιο."""
    for table in (POINT_NAMES, SIGN_NAMES, ASPECT_NAMES, WEIGHT_NAMES):
        if greek_name in table:
            return table[greek_name]
    return greek_name
