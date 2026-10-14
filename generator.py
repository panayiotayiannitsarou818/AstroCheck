"""Αυτόματη δημιουργία ανάλυσης και τελικής αναδιατύπωσης μέσω Claude ή OpenAI,
με αυτόματο κύκλο διόρθωσης.

Ροή: δημιουργία → μηχανικός έλεγχος → αν αποτύχει, τα αναλυτικά σφάλματα
στέλνονται πίσω στο μοντέλο για στοχευμένη διόρθωση → νέος έλεγχος. Ο κύκλος
σταματά μόλις η ανάλυση περάσει ή όταν εξαντληθούν οι γύροι. Έτσι ο χρήστης
δεν χρειάζεται να κάνει χειροκίνητα το «κατέβασε – επικόλλησε – ανέβασε».
"""

from dataclasses import dataclass, field

from house_framework import already_in, framework_block
from typing import Callable, Optional

DEFAULT_MODEL = "gpt-5.4"
# v16: ο κύκλος συνεχίζει ΜΕΧΡΙ ΝΑ ΕΓΚΡΙΘΕΙ το κείμενο. Η προεπιλογή είναι ένα
# πολύ υψηλό δίχτυ ασφαλείας (κόστος/χρόνος), μόνο για την περίπτωση που ο
# έλεγχος απορρίπτει λανθασμένα κάτι που το μοντέλο δεν μπορεί να διορθώσει.
# Secrets: AUTO_MAX_ROUNDS = αριθμός (1–100) ή 0 = χωρίς κανένα όριο.
DEFAULT_MAX_ROUNDS = 30
MAX_ROUNDS_LIMIT = 100
UNLIMITED = 0
REQUEST_TIMEOUT = 900  # δευτερόλεπτα ανά κλήση (μεγάλο κείμενο 12 Οίκων)

REVISION_TEMPLATE = """Ακολουθεί η δεσμευτική εντολή, η ανάλυση που παρήγαγες και τα σφάλματα που εντόπισε ο μηχανικός έλεγχος του AstroCheck Pro.

Διόρθωσε ΜΟΝΟ τα σημεία που αναφέρονται στα σφάλματα, ακολουθώντας πιστά τη δεσμευτική εντολή και τα ελεγμένα δεδομένα της. Μην αλλάξεις τίποτε άλλο: όψεις, orb, κατηγορίες βαρύτητας, Οίκοι, κυβερνήτες, ενότητες και ερμηνευτικό περιεχόμενο που δεν σχετίζονται με τα σφάλματα μένουν αυτούσια. Μην προσθέσεις νέες πληροφορίες.

Επέστρεψε ΟΛΟΚΛΗΡΗ τη διορθωμένη ανάλυση, από την αρχή μέχρι το τέλος, χωρίς σχόλια, εισαγωγή ή επεξήγηση των αλλαγών.

=== ΣΦΑΛΜΑΤΑ ΕΛΕΓΧΟΥ (ΔΕΔΟΜΕΝΑ, ΔΟΜΗ, ΠΕΡΙΕΧΟΜΕΝΟ) ===
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
    usage = getattr(response, "usage", None)
    return ModelText.build(
        response.output_text,
        getattr(usage, "input_tokens", 0),
        getattr(usage, "output_tokens", 0),
    )


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

    input_tokens = 0
    output_tokens = 0


# ---------------------------------------------------------------------------
# v18: κατανάλωση, κόστος και όρια διακοπής
# ---------------------------------------------------------------------------
class ModelText(str):
    """Το κείμενο της απάντησης, μαζί με τα tokens που χρεώθηκαν."""

    input_tokens = 0
    output_tokens = 0

    @classmethod
    def build(cls, text: str, input_tokens=0, output_tokens=0) -> "ModelText":
        t = cls(text)
        t.input_tokens = int(input_tokens or 0)
        t.output_tokens = int(output_tokens or 0)
        return t


# Τιμές σε δολάρια ανά 1 εκατομμύριο tokens (είσοδος, έξοδος). Η «σκέψη» του
# μοντέλου χρεώνεται ως έξοδος. Μοντέλο εκτός πίνακα χωρίς τιμή στα Secrets:
# φαίνονται μόνο τα tokens και το όριο κόστους δεν μπορεί να εφαρμοστεί.
PRICES_USD_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    # v19: ενδεικτική τιμή OpenAI (δημόσιοι τιμοκατάλογοι, Οκτ. 2026)· αν διαφέρει,
    # όρισε PRICE_INPUT_PER_MTOK / PRICE_OUTPUT_PER_MTOK στα Secrets.
    "gpt-5.4": (2.5, 15.0),
}
# Ενδεικτική ισοτιμία για την εμφάνιση σε ευρώ (Secrets: EUR_PER_USD).
DEFAULT_EUR_PER_USD = 0.86
# Εκτίμηση εξόδου (tokens, μαζί με τη «σκέψη») για το ΠΡΩΤΟ αίτημα, πριν υπάρξει
# μέτρηση· χρησιμοποιείται μόνο για τον έλεγχο ορίου κόστους πριν από την κλήση.
FIRST_CALL_OUTPUT_ESTIMATE = 40_000
CHARS_PER_TOKEN = 2.5  # ελληνικό κείμενο: περίπου 2–3 χαρακτήρες ανά token


def price_for(model: str, override=None):
    """(είσοδος, έξοδος) σε $ ανά 1M tokens. Το μοντέλο πρέπει να ταιριάζει
    ακριβώς (επιτρέπεται κατάληξη ημερομηνίας), ώστε π.χ. το «gpt-5.4-mini»
    να ΜΗ χρεώνεται με την τιμή του «gpt-5.4»."""
    import re as _re

    m = (model or "").strip().lower()
    for name, price in PRICES_USD_PER_MTOK.items():
        if _re.fullmatch(_re.escape(name) + r"(?:-\d{8}|-\d{4}-\d{2}-\d{2})?", m):
            return price
    return override


@dataclass
class Usage:
    """Αθροιστική κατανάλωση ενός πελάτη. Το ίδιο αντικείμενο μοιράζεται σε
    όλα τα στάδια (ανάλυση, τελικό έντυπο, έλεγχος περιεχομένου, γύροι
    ποιότητας), ώστε το όριο κόστους να αφορά το σύνολο."""

    model: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    price_override: Optional[tuple] = None  # (είσοδος, έξοδος) για μοντέλα εκτός πίνακα
    spent_usd: float = 0.0
    unpriced_requests: int = 0
    main_requests: int = 0  # αιτήματα δημιουργίας/διόρθωσης (όχι ελέγχου)
    main_spent_usd: float = 0.0
    review_requests: int = 0  # v19.3: αιτήματα του ελέγχου περιεχομένου
    review_spent_usd: float = 0.0

    def price(self, model: str = ""):
        return price_for(model or self.model, self.price_override)

    def add(self, text, model: str = "", main: bool = True) -> None:
        self.requests += 1
        inp = int(getattr(text, "input_tokens", 0) or 0)
        out = int(getattr(text, "output_tokens", 0) or 0)
        self.input_tokens += inp
        self.output_tokens += out
        price = self.price(model)
        if price is None:
            if inp or out:
                self.unpriced_requests += 1
            return
        cost = (inp * price[0] + out * price[1]) / 1_000_000
        self.spent_usd += cost
        if main:
            self.main_requests += 1
            self.main_spent_usd += cost
        else:
            self.review_requests += 1
            self.review_spent_usd += cost

    def add_failure(self, exc, model: str = "", main: bool = True) -> None:
        """Αίτημα που απέτυχε αφού χρεώθηκε (π.χ. κομμένη απάντηση). v19.6: με το
        ΣΩΣΤΟ μοντέλο και είδος (ο ελεγκτής Sonnet δεν χρεώνεται ως Opus)."""
        if getattr(exc, "input_tokens", 0) or getattr(exc, "output_tokens", 0):
            self.add(exc, model, main)

    @property
    def cost_usd(self):
        if not self.spent_usd and (self.unpriced_requests or not self.requests or self.price() is None):
            return None
        return self.spent_usd

    def estimate_next_usd(self, request_text: str = ""):
        """Εκτίμηση κόστους του επόμενου αιτήματος δημιουργίας/διόρθωσης."""
        if self.main_requests:
            return self.main_spent_usd / self.main_requests
        price = self.price()
        if price is None:
            return None
        inp = len(request_text) / CHARS_PER_TOKEN
        return (inp * price[0] + FIRST_CALL_OUTPUT_ESTIMATE * price[1]) / 1_000_000

    def estimate_review_usd(self, request_text: str, model: str, output_estimate: int):
        """v19.3: εκτίμηση κόστους της επόμενης κλήσης του ελέγχου περιεχομένου."""
        price = self.price(model)
        if price is None:
            return None
        inp = len(request_text) / CHARS_PER_TOKEN
        first = (inp * price[0] + output_estimate * price[1]) / 1_000_000
        if self.review_requests:
            return max(first, self.review_spent_usd / self.review_requests)
        return first

    def describe(self, eur_per_usd: float = DEFAULT_EUR_PER_USD) -> str:
        tokens = f"{self.requests} αιτήματα · {self.input_tokens:,} tokens εισόδου · {self.output_tokens:,} tokens εξόδου".replace(",", ".")
        cost = self.cost_usd
        if cost is None:
            return tokens + " · κόστος: άγνωστη τιμή μοντέλου"
        eur = f"{cost * eur_per_usd:.2f}".replace(".", ",")
        usd = f"{cost:.2f}".replace(".", ",")
        prefix = "τουλάχιστον" if self.unpriced_requests else "περίπου"
        return f"{tokens} · κόστος {prefix} {eur} € ({usd} $)"


class PermanentAPIError(RuntimeError):
    """Σφάλμα που ΔΕΝ διορθώνεται με νέα προσπάθεια (λάθος κλειδί, μοντέλο που
    δεν υπάρχει, χωρίς υπόλοιπο, μη έγκυρο αίτημα). Ο κύκλος σταματά αμέσως."""


_PERMANENT_NAMES = {
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "BadRequestError",
    "UnprocessableEntityError",
}
_PERMANENT_STATUS = {400, 401, 403, 404, 422}


def is_permanent_error(exc: BaseException) -> bool:
    if isinstance(exc, PermanentAPIError):
        return True
    if type(exc).__name__ in _PERMANENT_NAMES:
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status in _PERMANENT_STATUS


def explain_permanent_error(exc: BaseException) -> str:
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    if name == "AuthenticationError" or status == 401:
        return "Το κλειδί API δεν είναι έγκυρο. Έλεγξε το κλειδί στα Secrets."
    if name == "PermissionDeniedError" or status == 403:
        return "Το κλειδί API δεν έχει πρόσβαση σε αυτό το μοντέλο."
    if name == "NotFoundError" or status == 404:
        return "Το μοντέλο δεν βρέθηκε. Έλεγξε το όνομα του μοντέλου στα Secrets."
    if "credit" in text or "balance" in text or "quota" in text or "billing" in text:
        return "Δεν υπάρχει διαθέσιμο υπόλοιπο στον λογαριασμό API."
    return "Ο πάροχος απέρριψε το αίτημα ως μη έγκυρο."


# Διακοπή όταν ο κύκλος δεν προοδεύει (Secrets: AUTO_STALL_ROUNDS).
DEFAULT_STALL_ROUNDS = 6
# Διαδοχικά αποτυχημένα αιτήματα (δίκτυο, υπερφόρτωση) πριν τη διακοπή.
MAX_CONSECUTIVE_FAILURES = 5

STOP_STALLED = "στασιμότητα"
STOP_BUDGET = "όριο κόστους"
STOP_FAILURES = "επαναλαμβανόμενα αποτυχημένα αιτήματα"
STOP_ROUNDS = "όριο γύρων"
STOP_REVIEW = "ο έλεγχος περιεχομένου δεν ολοκληρώθηκε"
STOP_PERMANENT = "μόνιμο σφάλμα API"


def stall_rounds_from(value) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_STALL_ROUNDS
    return max(2, min(50, n))


def cost_limit_from(value):
    """Όριο κόστους σε δολάρια ανά πελάτη (Secrets: AUTO_MAX_COST_USD). Κενό = χωρίς."""
    try:
        v = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


# v17.1: επίπεδο προσπάθειας (effort). Στο Claude Opus 5.5 η σκέψη (adaptive
# thinking) είναι πάντα ενεργή, αλλά η προεπιλογή είναι «medium». Για κείμενο
# 12 Οίκων με αυστηρούς κανόνες ζητάμε «high». Secrets: ANTHROPIC_EFFORT
# (low / medium / high / xhigh / max). Κενό = προεπιλογή του μοντέλου.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_EFFORT = "high"


def effort_from(value) -> str:
    v = str(value or "").strip().lower()
    if v in ("", "default", "none", "0"):
        return DEFAULT_EFFORT if v == "" else ""
    return v if v in EFFORT_LEVELS else DEFAULT_EFFORT


def _anthropic_stream(client, model: str, text: str, effort: str):
    kwargs = dict(model=model, max_tokens=ANTHROPIC_MAX_TOKENS, messages=[{"role": "user", "content": text}])
    if effort:
        # extra_body: λειτουργεί ανεξάρτητα από την έκδοση του SDK
        kwargs["extra_body"] = {"output_config": {"effort": effort}}
    # Ροή (stream): οι μεγάλες απαντήσεις δεν επιτρέπονται χωρίς αυτήν.
    with client.messages.stream(**kwargs) as stream:
        return stream.get_final_message()


def _anthropic_complete(api_key: str, text: str, model: str, effort: str = DEFAULT_EFFORT) -> str:
    import anthropic

    bad_request = getattr(anthropic, "BadRequestError", None) or ()
    client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)
    try:
        message = _anthropic_stream(client, model, text, effort)
    except bad_request as exc:
        # Μοντέλο χωρίς υποστήριξη effort: νέα προσπάθεια με την προεπιλογή του.
        if effort and ("effort" in str(exc).lower() or "output_config" in str(exc).lower()):
            message = _anthropic_stream(client, model, text, "")
        else:
            raise
    usage = getattr(message, "usage", None)
    if message.stop_reason == "max_tokens":
        exc = TruncatedOutput("Το κείμενο κόπηκε πριν ολοκληρωθεί (όριο εξόδου του μοντέλου).")
        # v19: η κομμένη απάντηση χρεώνεται -- καταγράφεται στον μετρητή
        exc.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        exc.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        raise exc
    return ModelText.build(
        "".join(block.text for block in message.content if block.type == "text"),
        getattr(usage, "input_tokens", 0),
        getattr(usage, "output_tokens", 0),
    )


def completer(provider: str, effort: str = DEFAULT_EFFORT) -> Callable[[str, str, str], str]:
    """Η συνάρτηση κλήσης για τον πάροχο («Claude» ή «OpenAI»)."""
    if provider == "Claude":
        return lambda api_key, text, model: _anthropic_complete(api_key, text, model, effort)
    if provider == "OpenAI":
        return _openai_complete
    raise ValueError(f"Άγνωστος πάροχος: {provider}")


def max_rounds_from(value) -> int:
    """Όριο ασφαλείας γύρων από ρύθμιση (π.χ. Secrets). Άκυρη τιμή -> προεπιλογή."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_ROUNDS
    if n == UNLIMITED:
        return UNLIMITED
    return max(1, min(MAX_ROUNDS_LIMIT, n))


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
    # v18: γιατί σταμάτησε ο κύκλος χωρίς επιτυχία (None αν πέρασε)
    stop_reason: Optional[str] = None
    usage: Optional[Usage] = None

    @property
    def ok(self) -> bool:
        return bool(getattr(self.validation, "ok", False))


POLISH_TEMPLATE = """Ακολουθεί η δεσμευτική εντολή και ένα κείμενο που ΗΔΗ ΕΓΚΡΙΘΗΚΕ από τον μηχανικό έλεγχο του AstroCheck Pro, μαζί με παρατηρήσεις ποιότητας ύφους που δεν κλείδωσαν την έγκριση.

Βελτίωσε ΜΟΝΟ όσα αφορούν οι παρατηρήσεις, ώστε το κείμενο να ακολουθεί πληρέστερα την εντολή. Μην αλλάξεις κανένα αστρολογικό δεδομένο, όψη, κυβερνήτη, Οίκο ή ενότητα· μην αφαιρέσεις ερμηνευτικό νόημα και μην προσθέσεις νέο. Ό,τι δεν αφορούν οι παρατηρήσεις μένει αυτούσιο.

Επέστρεψε ΟΛΟΚΛΗΡΟ το κείμενο, από την αρχή μέχρι το τέλος, χωρίς σχόλια, εισαγωγή ή επεξήγηση των αλλαγών.

=== ΠΑΡΑΤΗΡΗΣΕΙΣ ΠΟΙΟΤΗΤΑΣ ===
{errors}

=== ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ ===
{prompt}

=== ΕΓΚΕΚΡΙΜΕΝΟ ΚΕΙΜΕΝΟ ΠΡΟΣ ΒΕΛΤΙΩΣΗ ===
{analysis}
"""


def _quality_notes(result) -> list:
    from content_review import REVIEW_FAILED_PREFIX

    return [
        str(w)
        for w in (getattr(result, "warnings", None) or [])
        if not str(w).startswith(REVIEW_FAILED_PREFIX)
    ]


def generate_validated(
    api_key: str,
    prompt: str,
    validate: Callable[[str], object],
    model: str = DEFAULT_MODEL,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    on_round: Optional[Callable[[Round], None]] = None,
    complete: Optional[Callable[[str, str, str], str]] = None,
    revision_template: str = "",
    polish: bool = False,
    stall_rounds: int = DEFAULT_STALL_ROUNDS,
    usage: Optional[Usage] = None,
    max_cost_usd: Optional[float] = None,
    start_text: str = "",
    on_best: Optional[Callable[[str, bool], None]] = None,
) -> GenerationOutcome:
    """Δημιουργία με αυτόματο κύκλο διόρθωσης μέχρι να περάσει ο έλεγχος.

    v19.5 — συνέχεια: με `start_text` (το καλύτερο κείμενο μιας διαδικασίας που
    διακόπηκε) ΔΕΝ γράφεται νέο κείμενο από την αρχή· ο πρώτος γύρος απλώς
    ελέγχει το υπάρχον και οι διορθώσεις συνεχίζουν από εκεί. Αν η διαδικασία
    διακοπεί από μόνιμο σφάλμα (π.χ. τέλος υπολοίπου), το PermanentAPIError
    κουβαλά στο `.partial` την καλύτερη απόπειρα ως τότε.

    `validate(text)` επιστρέφει αντικείμενο με `.ok`, `.summary()` και
    `.details_lines()` (π.χ. validator.validate_analysis).
    Επιστρέφεται το πρώτο κείμενο που περνά· αλλιώς εκείνο με τα λιγότερα
    σφάλματα, ώστε ο χρήστης να βλέπει την καλύτερη απόπειρα.

    v18 — ο κύκλος σταματά νωρίτερα (χωρίς να χάνεται η καλύτερη απόπειρα):
    - αμέσως σε μόνιμο σφάλμα API (λάθος κλειδί, ανύπαρκτο μοντέλο, χωρίς
      υπόλοιπο): σηκώνεται PermanentAPIError·
    - όταν για `stall_rounds` συνεχόμενους γύρους δεν μειώνονται τα σφάλματα
      κάτω από την καλύτερη ως τώρα απόπειρα (στασιμότητα)·
    - μετά από MAX_CONSECUTIVE_FAILURES αποτυχημένα αιτήματα στη σειρά·
    - όταν το συνολικό κόστος ξεπεράσει το `max_cost_usd` (αν οριστεί).
    `usage`: κοινός μετρητής κατανάλωσης (μπορεί να μοιράζεται σε στάδια).
    `complete` επιτρέπει σε tests να αντικαταστήσουν την κλήση στο μοντέλο.
    """
    complete = complete or _openai_complete
    usage = usage if usage is not None else Usage(model=model)
    if not usage.model:
        usage.model = model
    rounds = []
    best = None
    text = ""
    result = None
    n = 0
    no_progress = 0
    failures = 0
    stop_reason = None

    def _record(info):
        rounds.append(info)
        if on_round:
            on_round(info)

    def _call(request_text):
        try:
            out = complete(api_key, request_text, model)
        except Exception as exc:
            usage.add_failure(exc, model)
            raise
        usage.add(out, model)
        return out

    def _no_budget_for(request_text) -> bool:
        """v19: ο έλεγχος ορίου γίνεται ΠΡΙΝ από την κλήση, με εκτίμηση κόστους."""
        if not max_cost_usd:
            return False
        estimate = usage.estimate_next_usd(request_text)
        if estimate is None:
            return False
        return usage.spent_usd + estimate > max_cost_usd

    def _permanent(exc):
        """Μόνιμο σφάλμα: η καλύτερη απόπειρα ως τώρα ΔΕΝ χάνεται."""
        err = PermanentAPIError(explain_permanent_error(exc))
        if best is not None:
            err.partial = GenerationOutcome(best[1], best[2], rounds, STOP_PERMANENT, usage)
        return err

    while max_rounds == UNLIMITED or n < max(1, max_rounds):
        n += 1
        if n == 1 and start_text.strip():
            text = start_text
            kind = "συνέχεια"
        elif n == 1:
            if _no_budget_for(prompt):
                raise PermanentAPIError(
                    "Το όριο κόστους (AUTO_MAX_COST_USD) είναι μικρότερο από το εκτιμώμενο κόστος του "
                    "πρώτου αιτήματος· αύξησέ το ή άφησέ το κενό."
                )
            try:
                text = _call(prompt)
            except Exception as exc:
                if is_permanent_error(exc):
                    raise _permanent(exc) from exc
                raise
            kind = "δημιουργία"
        else:
            # v14: η διόρθωση ξεκινά από την ΚΑΛΥΤΕΡΗ ως τώρα απόπειρα, όχι από
            # την τελευταία -- αν ένας γύρος χειροτέρεψε το κείμενο, δεν
            # χτίζουμε πάνω του.
            _, base_text, base_result = best
            request = revision_prompt(prompt, base_text, base_result.details_lines(), revision_template)
            if _no_budget_for(request):
                stop_reason = STOP_BUDGET
                break
            try:
                text = _call(request)
            except Exception as exc:  # v16: ένα αποτυχημένο αίτημα δεν σταματά τον κύκλο
                if is_permanent_error(exc):
                    raise _permanent(exc) from exc
                failures += 1
                _record(Round(n, "διόρθωση", False, best[0], f"Το αίτημα απέτυχε ({type(exc).__name__}) — νέα προσπάθεια."))
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    stop_reason = STOP_FAILURES
                    break
                continue
            kind = "διόρθωση"
        failures = 0
        result = validate(text)
        errors = len(result.details_lines())
        _record(Round(n, kind, bool(result.ok), errors, result.summary()))
        if best is None or errors < best[0]:
            best = (errors, text, result)
            no_progress = 0
            if on_best:  # v19.6: αποθήκευση προόδου ΑΜΕΣΩΣ, πριν από κάθε επόμενη κλήση
                on_best(text, bool(result.ok))
        else:
            no_progress += 1
        if getattr(result, "review_incomplete", False):
            # v19.2: ο ελεγκτής ΤΝ δεν απάντησε έγκυρα -- δεν στέλνεται το κείμενο για
            # «διόρθωση» (δεν υπάρχει τι να διορθωθεί), ούτε περνά ως ελεγμένο.
            best = (errors, text, result)
            if on_best:
                on_best(text, False)
            stop_reason = STOP_BUDGET if getattr(result, "budget_exhausted", False) else STOP_REVIEW
            break
        if result.ok:
            polish_request = revision_prompt(prompt, text, _quality_notes(result), POLISH_TEMPLATE)
            if polish and _quality_notes(result) and not _no_budget_for(polish_request):
                outcome = _polish(api_key, prompt, validate, model, complete, text, result, rounds, n + 1, on_round, usage)
                if on_best and outcome.text != text:
                    on_best(outcome.text, True)
                return outcome
            return GenerationOutcome(text, result, rounds, None, usage)
        if no_progress >= max(2, stall_rounds):
            stop_reason = STOP_STALLED
            break
    else:
        stop_reason = STOP_ROUNDS
    if best is None:  # μόνο αν απέτυχαν όλα τα αιτήματα πριν από κάθε έλεγχο
        raise RuntimeError("Κανένα αίτημα δεν ολοκληρώθηκε.")
    _, best_text, best_result = best
    return GenerationOutcome(best_text, best_result, rounds, stop_reason, usage)


def _over_budget(usage: Usage, max_cost_usd) -> bool:
    if not max_cost_usd:
        return False
    estimate = usage.estimate_next_usd()
    return estimate is not None and usage.spent_usd + estimate > max_cost_usd


def _polish(api_key, prompt, validate, model, complete, text, result, rounds, number, on_round, usage=None):
    """v17.1: ένας γύρος ποιότητας ΜΕΤΑ την έγκριση. Οι παρατηρήσεις ύφους του
    ελέγχου (δεν κλειδώνουν) στέλνονται για βελτίωση. Το νέο κείμενο κρατιέται
    ΜΟΝΟ αν εξακολουθεί να περνά τον έλεγχο, έχει λιγότερες παρατηρήσεις ΚΑΙ
    δεν έχει χάσει σημαντικό μέρος του κειμένου (v18: έως 10% συντομότερο)·
    αλλιώς μένει το ήδη ελεγμένο κείμενο."""
    usage = usage if usage is not None else Usage(model=model)
    notes = _quality_notes(result)
    try:
        try:
            polished = complete(api_key, revision_prompt(prompt, text, notes, POLISH_TEMPLATE), model)
        except Exception as exc:
            usage.add_failure(exc, model)
            raise
        usage.add(polished, model)
        new_result = validate(polished)
    except Exception as exc:
        info = Round(number, "γύρος ποιότητας", True, 0, f"Δεν ολοκληρώθηκε ({type(exc).__name__}) — κρατήθηκε το ελεγμένο κείμενο.")
        rounds.append(info)
        if on_round:
            on_round(info)
        return GenerationOutcome(text, result, rounds, None, usage)
    lost = len(text.split()) - len(polished.split())
    kept_length = not (lost > 30 and lost > 0.1 * len(text.split()))
    better = bool(new_result.ok) and len(_quality_notes(new_result)) < len(notes) and kept_length
    reason = "" if kept_length else " (το νέο κείμενο ήταν αισθητά συντομότερο)"
    info = Round(
        number,
        "γύρος ποιότητας",
        True,
        0,
        f"Παρατηρήσεις ποιότητας {len(notes)} → {len(_quality_notes(new_result))}: "
        + ("κρατήθηκε το βελτιωμένο κείμενο." if better else f"κρατήθηκε το ήδη ελεγμένο κείμενο{reason}."),
    )
    rounds.append(info)
    if on_round:
        on_round(info)
    if better:
        return GenerationOutcome(polished, new_result, rounds, None, usage)
    return GenerationOutcome(text, result, rounds, None, usage)


# ---------------------------------------------------------------------------
# v15: αυτόματη ΤΕΛΙΚΗ ΑΝΑΔΙΑΤΥΠΩΣΗ (το δεύτερο χειροκίνητο βήμα).
# ---------------------------------------------------------------------------
REWRITE_REVISION_TEMPLATE = """Ακολουθεί η Δεσμευτική Εντολή Τελικής Αναδιατύπωσης με την ελεγμένη τεχνική ανάλυση, το τελικό έντυπο που παρήγαγες και τα σφάλματα που εντόπισε ο μηχανικός έλεγχος του AstroCheck Pro.

Διόρθωσε ΜΟΝΟ τα σημεία που αναφέρονται στα σφάλματα, με μοναδική πηγή την ελεγμένη τεχνική ανάλυση. Μην αλλάξεις τίποτε άλλο και μην προσθέσεις νέο αστρολογικό ή προσωπικό νόημα.

Επέστρεψε ΟΛΟΚΛΗΡΟ το διορθωμένο τελικό έντυπο, από την αρχή μέχρι το τέλος, σε απλό κείμενο, χωρίς σχόλια, εισαγωγή ή επεξήγηση των αλλαγών.

=== ΣΦΑΛΜΑΤΑ ΕΛΕΓΧΟΥ (ΔΕΔΟΜΕΝΑ, ΔΟΜΗ, ΠΕΡΙΕΧΟΜΕΝΟ) ===
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
    ]
    if not already_in(rules):  # v19.1: μόνο αν η εντολή δεν έχει ήδη το πλαίσιο Οίκων
        parts += [
            "=== ΠΛΑΙΣΙΟ ΟΙΚΩΝ ===",
            framework_block()
            + "\nΣτο τελικό έντυπο το πλαίσιο ισχύει για το ΝΟΗΜΑ: κράτα τις βασικές ερμηνείες κάθε Οίκου "
            "της ελεγμένης πηγής, χωρίς νέα συμπεράσματα, γενικόλογο γέμισμα ή επαναλήψεις.",
        ]
    parts += [
        "=== ΜΟΡΦΗ ΠΑΡΑΔΟΣΗΣ ===",
        "Επέστρεψε ΜΟΝΟ το κείμενο του τελικού εντύπου, σε απλό κείμενο, χωρίς εισαγωγή, σχόλια ή "
        "αναφορά στον αυτοέλεγχο. Κάθε τίτλος Οίκου και κάθε τίτλος ενότητας σε δική του γραμμή. "
        "Το Word δημιουργείται από την εφαρμογή. "
        "Η όψη 150° γράφεται στο έντυπο μόνο ως «χιαστί όψη» (στα αγγλικά «quincunx»), χωρίς τον "
        "αριθμό «150°», γιατί ο έλεγχος απορρίπτει κάθε μοίρα στο έντυπο του πελάτη (κανόνας 20). "
        "Ο έλεγχος απορρίπτει επίσης διαγνώσεις υγείας, βέβαιες προβλέψεις («σίγουρα θα…», «θα αποτύχει»), "
        "μοιρολατρία («είσαι προορισμένη») και απόλυτα επαγγελματικά συμπεράσματα («πρέπει να γίνεις…»): "
        "γράψε τάσεις και δυνατότητες με «μπορεί», «ενδέχεται», «ίσως».",
        "=== " + _SOURCE_HEADING.upper() + " ===",
        analysis_text.strip(),
    ]
    return "\n\n".join(parts)
