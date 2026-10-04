"""Αυτόματη δημιουργία ανάλυσης μέσω OpenAI, με αυτόματο κύκλο διόρθωσης.

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


def generate_analysis(api_key: str, prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Μία απλή δημιουργία, χωρίς έλεγχο (διατηρείται για συμβατότητα)."""
    return _openai_complete(api_key, prompt, model)


def revision_prompt(prompt: str, analysis: str, error_lines: list) -> str:
    errors = "\n".join(f"- {line}" for line in error_lines) or "- (χωρίς λεπτομέρειες)"
    # .replace αντί για .format στο περιεχόμενο: η εντολή/ανάλυση μπορεί να
    # περιέχει άγκιστρα {} που θα έσπαγαν το str.format.
    return (
        REVISION_TEMPLATE.replace("{errors}", errors)
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
                api_key, revision_prompt(prompt, base_text, base_result.details_lines()), model
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
