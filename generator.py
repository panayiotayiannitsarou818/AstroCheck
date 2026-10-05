"""Αυτόματη δημιουργία ανάλυσης και τελικής αναδιατύπωσης μέσω Claude ή OpenAI,
με αυτόματο κύκλο διόρθωσης.

Ροή: δημιουργία → μηχανικός έλεγχος → αν αποτύχει, τα αναλυτικά σφάλματα
στέλνονται πίσω στο μοντέλο για στοχευμένη διόρθωση → νέος έλεγχος. Ο κύκλος
σταματά μόλις η ανάλυση περάσει ή όταν εξαντληθούν οι γύροι. Έτσι ο χρήστης
δεν χρειάζεται να κάνει χειροκίνητα το «κατέβασε – επικόλλησε – ανέβασε».
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_MODEL = "gpt-5.4"
DEFAULT_MAX_ROUNDS = 3  # 1 δημιουργία + έως 2 διορθώσεις (όριο κόστους)
REQUEST_TIMEOUT = 900  # δευτερόλεπτα ανά κλήση (μεγάλο κείμενο 12 Οίκων)

REVISION_TEMPLATE = """Ακολουθεί η δεσμευτική εντολή, η ανάλυση που παρήγαγες και τα σφάλματα που εντόπισε ο μηχανικός έλεγχος του AstroCheck Pro.

Διόρθωσε ΜΟΝΟ τα σημεία που αναφέρονται στα σφάλματα, ακολουθώντας πιστά τη δεσμευτική εντολή και τα ελεγμένα δεδομένα της. Μην αλλάξεις τίποτε άλλο: όψεις, orb, κατηγορίες βαρύτητας, Οίκοι, κυβερνήτες, ενότητες και ερμηνευτικό περιεχόμενο που δεν σχετίζονται με τα σφάλματα μένουν αυτούσια. Μην προσθέσεις νέες πληροφορίες.

Επέστρεψε ΟΛΟΚΛΗΡΗ τη διορθωμένη ανάλυση, από την αρχή μέχρι το τέλος, χωρίς σχόλια, εισαγωγή ή επεξήγηση των αλλαγών.

=== ΣΦΑΛΜΑΤΑ ΜΗΧΑΝΙΚΟΥ ΕΛΕΓΧΟΥ ===
{errors}

=== ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ ===
{prompt}

=== ΑΝΑΛΥΣΗ ΠΡΟΣ ΔΙΟΡΘΩΣΗ ===
{analysis}
"""


def _openai_complete(api_key: str, text: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)
    response = client.responses.create(
        model=model,
        input=text,
        reasoning={"effort": "high"},
        text={"verbosity": "high"},
    )
    return response.output_text


# ---------------------------------------------------------------------------
# v15: δύο πάροχοι. Ο χρήστης διαλέγει ποιο μοντέλο γράφει.
# ---------------------------------------------------------------------------
PROVIDERS = ("Claude", "OpenAI")
DEFAULT_MODELS = {"Claude": "claude-opus-5-5", "OpenAI": DEFAULT_MODEL}
# (όνομα secret για το κλειδί, όνομα secret για το μοντέλο, υπόδειγμα κλειδιού)
PROVIDER_SETTINGS = {
    "Claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "sk-ant-..."),
    "OpenAI": ("OPENAI_API_KEY", "OPENAI_MODEL", "sk-..."),
}
# Το κείμενο 12 Οίκων είναι μεγάλο· το όριο αφήνει χώρο και για τη σκέψη του
# μοντέλου (μέγιστη έξοδος των τρεχόντων μοντέλων Claude: 128K tokens).
ANTHROPIC_MAX_TOKENS = 100_000


class TruncatedOutput(RuntimeError):
    """Το μοντέλο σταμάτησε επειδή εξαντλήθηκε το όριο εξόδου."""


def _anthropic_complete(api_key: str, text: str, model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)
    # Ροή (stream): οι μεγάλες απαντήσεις δεν επιτρέπονται χωρίς αυτήν.
    with client.messages.stream(
        model=model,
        max_tokens=ANTHROPIC_MAX_TOKENS,
        messages=[{"role": "user", "content": text}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "max_tokens":
        raise TruncatedOutput("Το κείμενο κόπηκε πριν ολοκληρωθεί (όριο εξόδου του μοντέλου).")
    return "".join(block.text for block in message.content if block.type == "text")


def completer(provider: str) -> Callable[[str, str, str], str]:
    """Η συνάρτηση κλήσης για τον πάροχο («Claude» ή «OpenAI»)."""
    if provider == "Claude":
        return _anthropic_complete
    if provider == "OpenAI":
        return _openai_complete
    raise ValueError(f"Άγνωστος πάροχος: {provider}")


def generate_analysis(api_key: str, prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Μία απλή δημιουργία, χωρίς έλεγχο (διατηρείται για συμβατότητα)."""
    return _openai_complete(api_key, prompt, model)


def revision_prompt(prompt: str, analysis: str, error_lines: list, template: str = "") -> str:
    errors = "\n".join(f"- {line}" for line in error_lines) or "- (χωρίς λεπτομέρειες)"
    # .replace αντί για .format στο περιεχόμενο: η εντολή/ανάλυση μπορεί να
    # περιέχει άγκιστρα {} που θα έσπαγαν το str.format.
    return (
        (template or REVISION_TEMPLATE).replace("{errors}", errors)
        .replace("{prompt}", prompt)
        .replace("{analysis}", analysis)
    )


@dataclass
class Round:
    number: int
    kind: str  # "δημιουργία" ή "διόρθωση"
    ok: bool
    error_count: int
    summary: str


@dataclass
class GenerationOutcome:
    text: str
    validation: object
    rounds: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(getattr(self.validation, "ok", False))


def generate_validated(
    api_key: str,
    prompt: str,
    validate: Callable[[str], object],
    model: str = DEFAULT_MODEL,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    on_round: Optional[Callable[[Round], None]] = None,
    complete: Optional[Callable[[str, str, str], str]] = None,
    revision_template: str = "",
) -> GenerationOutcome:
    """Δημιουργία με αυτόματο κύκλο διόρθωσης.

    `validate(text)` επιστρέφει αντικείμενο με `.ok`, `.summary()` και
    `.details_lines()` (π.χ. validator.validate_analysis).
    Επιστρέφεται η πρώτη ανάλυση που περνά· αν καμία δεν περάσει, εκείνη με
    τα λιγότερα σφάλματα, ώστε ο χρήστης να βλέπει την καλύτερη απόπειρα.
    `complete` επιτρέπει σε tests να αντικαταστήσουν την κλήση στο OpenAI.
    """
    complete = complete or _openai_complete
    rounds = []
    best = None
    text = ""
    result = None
    for n in range(1, max(1, max_rounds) + 1):
        if n == 1:
            text = complete(api_key, prompt, model)
            kind = "δημιουργία"
        else:
            # v14: η διόρθωση ξεκινά από την ΚΑΛΥΤΕΡΗ ως τώρα απόπειρα, όχι από
            # την τελευταία -- αν ένας γύρος χειροτέρεψε το κείμενο, δεν
            # χτίζουμε πάνω του.
            _, base_text, base_result = best
            text = complete(
                api_key,
                revision_prompt(prompt, base_text, base_result.details_lines(), revision_template),
                model,
            )
            kind = "διόρθωση"
        result = validate(text)
        errors = len(result.details_lines())
        info = Round(n, kind, bool(result.ok), errors, result.summary())
        rounds.append(info)
        if on_round:
            on_round(info)
        if best is None or errors < best[0]:
            best = (errors, text, result)
        if result.ok:
            return GenerationOutcome(text, result, rounds)
    _, best_text, best_result = best
    return GenerationOutcome(best_text, best_result, rounds)


# ---------------------------------------------------------------------------
# v15: αυτόματη ΤΕΛΙΚΗ ΑΝΑΔΙΑΤΥΠΩΣΗ (το δεύτερο χειροκίνητο βήμα).
# ---------------------------------------------------------------------------
REWRITE_REVISION_TEMPLATE = """Ακολουθεί η Δεσμευτική Εντολή Τελικής Αναδιατύπωσης με την ελεγμένη τεχνική ανάλυση, το τελικό έντυπο που παρήγαγες και τα σφάλματα που εντόπισε ο μηχανικός έλεγχος του AstroCheck Pro.

Διόρθωσε ΜΟΝΟ τα σημεία που αναφέρονται στα σφάλματα, με μοναδική πηγή την ελεγμένη τεχνική ανάλυση. Μην αλλάξεις τίποτε άλλο και μην προσθέσεις νέο αστρολογικό ή προσωπικό νόημα.

Επέστρεψε ΟΛΟΚΛΗΡΟ το διορθωμένο τελικό έντυπο, από την αρχή μέχρι το τέλος, σε απλό κείμενο, χωρίς σχόλια, εισαγωγή ή επεξήγηση των αλλαγών.

=== ΣΦΑΛΜΑΤΑ ΜΗΧΑΝΙΚΟΥ ΕΛΕΓΧΟΥ ===
{errors}

=== ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ ΚΑΙ ΕΛΕΓΜΕΝΗ ΑΝΑΛΥΣΗ ===
{prompt}

=== ΤΕΛΙΚΟ ΕΝΤΥΠΟ ΠΡΟΣ ΔΙΟΡΘΩΣΗ ===
{analysis}
"""

_COMMAND_START = "Η εντολή"
_COMMAND_LOG = "Ημερολόγιο διορθώσεων ανά ανάλυση"
_COMMAND_FINAL_CHECK = "ΥΠΟΧΡΕΩΤΙΚΟΣ ΤΕΛΙΚΟΣ ΕΛΕΓΧΟΣ ΑΜΕΤΑΒΛΗΤΩΝ ΔΕΔΟΜΕΝΩΝ"
_SOURCE_HEADING = "Ήδη ελεγμένη τεχνική ανάλυση — μοναδική πηγή περιεχομένου"


def rewrite_command_rules(command_text: str) -> str:
    """Οι κανόνες της Δεσμευτικής Εντολής, χωρίς τις οδηγίες χρήσης, τη θέση
    επικόλλησης και το ημερολόγιο διορθώσεων (που αφορούν τη χειροκίνητη ροή)."""
    start = command_text.find(_COMMAND_START)
    log = command_text.find(_COMMAND_LOG)
    check = command_text.find(_COMMAND_FINAL_CHECK)
    if start < 0 or log < 0 or check < 0:
        raise ValueError("Η Δεσμευτική Εντολή δεν έχει την αναμενόμενη δομή.")
    rules = command_text[start + len(_COMMAND_START) : log]
    source = rules.find(_SOURCE_HEADING)
    if source >= 0:
        rules = rules[:source]
    return rules.strip() + "\n\n" + command_text[check:].strip()


def build_rewrite_prompt(command_text: str, analysis_text: str, name: str, language_block: str) -> str:
    """Πλήρης εντολή αναδιατύπωσης για αποστολή μέσω API."""
    rules = rewrite_command_rules(command_text).replace("[ΟΝΟΜΑ]", name or "[ΟΝΟΜΑ]")
    parts = []
    if language_block.strip():
        parts.append(language_block.strip())
    parts += [
        "=== ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ ΤΕΛΙΚΗΣ ΑΝΑΔΙΑΤΥΠΩΣΗΣ ===",
        rules,
        "=== ΜΟΡΦΗ ΠΑΡΑΔΟΣΗΣ ===",
        "Επέστρεψε ΜΟΝΟ το κείμενο του τελικού εντύπου, σε απλό κείμενο, χωρίς εισαγωγή, σχόλια ή "
        "αναφορά στον αυτοέλεγχο. Κάθε τίτλος Οίκου και κάθε τίτλος ενότητας σε δική του γραμμή. "
        "Το Word δημιουργείται από την εφαρμογή.",
        "=== " + _SOURCE_HEADING.upper() + " ===",
        analysis_text.strip(),
    ]
    return "\n\n".join(parts)
