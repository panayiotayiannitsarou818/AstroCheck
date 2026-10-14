"""v17: πλήρης αυτόματη διαδικασία με ένα κουμπί.

Ο χρήστης ανεβάζει ΜΟΝΟ το Astrodienst PDF. Από εκεί και πέρα:

    ανάλυση 12 Οίκων → έλεγχος → (διόρθωση μέχρι να περάσει)
    → τελικό έντυπο πελάτη → έλεγχος → (διόρθωση μέχρι να περάσει)

v18: ο κύκλος σταματά νωρίτερα σε στασιμότητα, μόνιμο σφάλμα API ή όριο κόστους.

Το τελικό έντυπο ξεκινά ΜΟΝΟ αν εγκριθεί η ανάλυση, γιατί η Δεσμευτική Εντολή
Τελικής Αναδιατύπωσης απαιτεί ως πηγή ελεγμένη ανάλυση.

Το module δεν εξαρτάται από το Streamlit, ώστε να ελέγχεται με tests.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from generator import (
    DEFAULT_EFFORT,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_STALL_ROUNDS,
    REWRITE_REVISION_TEMPLATE,
    STOP_BUDGET,
    PermanentAPIError,
    _over_budget,
    Round,
    Usage,
    build_rewrite_prompt,
    completer,
    generate_validated,
)
from content_review import KIND_ANALYSIS, KIND_REWRITE, REVIEW_EFFORT, review_model_for, with_content_review
from prompts import build_master_prompt
from ui_texts import rewrite_language_block
from validator import validate_analysis, validate_rewrite

STAGE_ANALYSIS = "Ανάλυση"
STAGE_REWRITE = "Τελικό έντυπο"


@dataclass
class PipelineResult:
    analysis_text: str = ""
    analysis_validation: object = None
    analysis_rounds: list = field(default_factory=list)
    final_text: str = ""
    final_validation: object = None
    final_rounds: list = field(default_factory=list)
    # v18: γιατί σταμάτησε κάθε στάδιο (None = πέρασε) και συνολική κατανάλωση
    analysis_stop_reason: Optional[str] = None
    final_stop_reason: Optional[str] = None
    usage: Optional[Usage] = None

    @property
    def analysis_ok(self) -> bool:
        return bool(getattr(self.analysis_validation, "ok", False))

    @property
    def final_ok(self) -> bool:
        return bool(getattr(self.final_validation, "ok", False))

    @property
    def ok(self) -> bool:
        return self.analysis_ok and self.final_ok

    @property
    def stop_reason(self) -> Optional[str]:
        if not self.analysis_ok:
            return self.analysis_stop_reason
        if not self.final_ok:
            return self.final_stop_reason
        return None

    @property
    def stopped_at(self) -> Optional[str]:
        """Το στάδιο όπου σταμάτησε η διαδικασία χωρίς έγκριση (None αν εγκρίθηκαν όλα)."""
        if not self.analysis_ok:
            return STAGE_ANALYSIS
        if not self.final_ok:
            return STAGE_REWRITE
        return None


def run_full_pipeline(
    *,
    chart,
    personal: dict,
    language: str,
    instructions_text: str,
    style_text: str,
    instructions_name: str,
    style_name: str,
    rewrite_command_text: str,
    api_key: str,
    provider: str,
    model: str,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    effort: str = DEFAULT_EFFORT,
    stall_rounds: int = DEFAULT_STALL_ROUNDS,
    max_cost_usd: Optional[float] = None,
    on_round: Optional[Callable[[str, Round], None]] = None,
    complete: Optional[Callable[[str, str, str], str]] = None,
    usage: Optional[Usage] = None,
    content_review: bool = True,
    review_model: str = "",
    review_complete: Optional[Callable[[str, str, str], str]] = None,
    validate_analysis_fn: Callable = validate_analysis,
    validate_rewrite_fn: Callable = validate_rewrite,
    resume_analysis: str = "",
    resume_final: str = "",
    on_progress: Optional[Callable[[str, str, bool], None]] = None,
) -> PipelineResult:
    """Ανάλυση και τελικό έντυπο, το καθένα με κύκλο διόρθωσης μέχρι να εγκριθεί.

    `on_round(στάδιο, Round)` ενημερώνει την οθόνη μετά από κάθε γύρο.
    `complete`, `validate_*_fn`: αντικαθίστανται μόνο στα tests.

    v19.5 — συνέχεια από εκεί που σταμάτησε: `resume_analysis` / `resume_final`
    είναι τα καλύτερα κείμενα μιας προηγούμενης διακοπείσας εκτέλεσης. Η ανάλυση
    δεν ξαναγράφεται από την αρχή· το τελικό έντυπο συνεχίζεται μόνο αν η ανάλυση
    έμεινε ίδια (αλλιώς θα στηριζόταν σε παλιά πηγή). Σε μόνιμο σφάλμα (π.χ.
    τέλος υπολοίπου) το PermanentAPIError κουβαλά στο `.result` ό,τι έγινε ως τότε.
    v19.6: `on_progress(στάδιο, κείμενο, πέρασε)` καλείται ΑΜΕΣΩΣ κάθε φορά που
    βελτιώνεται το καλύτερο κείμενο ενός σταδίου, ώστε η πρόοδος να αποθηκεύεται
    πριν από την επόμενη κλήση — ανεξάρτητα από το είδος της επόμενης διακοπής.
    Κάθε σφάλμα (όχι μόνο μόνιμο) κουβαλά στο `.result` ό,τι ολοκληρώθηκε.
    """
    complete = complete or completer(provider, effort)
    # κοινός μετρητής: το όριο κόστους αφορά όλο τον πελάτη (και τις καρτέλες 2/3)
    usage = usage if usage is not None else Usage(model=model)
    if not usage.model:
        usage.model = model
    reviewer_model = review_model_for(provider, model, review_model)
    reviewer = review_complete or (completer(provider, REVIEW_EFFORT) if content_review else None)

    def _checked(validate, kind, source=""):
        """v19: μηχανικός έλεγχος + έλεγχος περιεχομένου με ΤΝ."""
        if not content_review:
            return validate
        return with_content_review(validate, reviewer, api_key, reviewer_model, kind, source, usage, max_cost_usd)

    result = PipelineResult(usage=usage)
    name = chart.name if getattr(chart, "name", "") else "[ΟΝΟΜΑ]"

    def _report(stage):
        return (lambda r: on_round(stage, r)) if on_round else None

    # 1. Ανάλυση των 12 Οίκων
    analysis_prompt = build_master_prompt(
        chart, personal, language, instructions_text, style_text, instructions_name, style_name
    )
    def _fail(exc, stage):
        partial = getattr(exc, "partial", None)
        if partial is not None:
            if stage == STAGE_ANALYSIS:
                result.analysis_text = partial.text
                result.analysis_validation = partial.validation
                result.analysis_rounds = partial.rounds
            else:
                result.final_text = partial.text
                result.final_validation = partial.validation
                result.final_rounds = partial.rounds
        try:
            exc.result = result
        except Exception:  # εξαιρέσεις που δεν δέχονται πεδία
            pass
        return exc

    try:
        analysis = generate_validated(
            api_key,
            analysis_prompt,
            validate=_checked(lambda t: validate_analysis_fn(chart, t, personal), KIND_ANALYSIS),
            model=model,
            max_rounds=max_rounds,
            on_round=_report(STAGE_ANALYSIS),
            complete=complete,
            # ένα κείμενο που συνεχίζεται έχει ήδη περάσει ενδεχομένως από γύρο ποιότητας
            polish=not resume_analysis.strip(),
            stall_rounds=stall_rounds,
            usage=usage,
            max_cost_usd=max_cost_usd,
            start_text=resume_analysis,
            on_best=(lambda t, ok: on_progress(STAGE_ANALYSIS, t, ok)) if on_progress else None,
        )
    except Exception as exc:
        raise _fail(exc, STAGE_ANALYSIS)
    result.analysis_stop_reason = analysis.stop_reason
    result.analysis_text = analysis.text
    result.analysis_validation = analysis.validation
    result.analysis_rounds = analysis.rounds
    if not analysis.ok:
        return result
    if _over_budget(usage, max_cost_usd):
        result.final_stop_reason = STOP_BUDGET
        return result
    analysis_same = bool(resume_analysis.strip()) and analysis.text == resume_analysis

    # 2. Τελικό έντυπο πελάτη, με πηγή την ΕΓΚΕΚΡΙΜΕΝΗ ανάλυση
    rewrite_prompt = build_rewrite_prompt(
        rewrite_command_text,
        analysis.text,
        name,
        rewrite_language_block(name, language, analysis.text),
    )
    try:
        final = generate_validated(
            api_key,
            rewrite_prompt,
            validate=_checked(
                lambda t: validate_rewrite_fn(chart, analysis.text, t, personal), KIND_REWRITE, analysis.text
            ),
            model=model,
            max_rounds=max_rounds,
            on_round=_report(STAGE_REWRITE),
            complete=complete,
            revision_template=REWRITE_REVISION_TEMPLATE,
            polish=True,
            stall_rounds=stall_rounds,
            usage=usage,
            max_cost_usd=max_cost_usd,
            start_text=resume_final if analysis_same else "",
            on_best=(lambda t, ok: on_progress(STAGE_REWRITE, t, ok)) if on_progress else None,
        )
    except Exception as exc:
        raise _fail(exc, STAGE_REWRITE)
    result.final_stop_reason = final.stop_reason
    result.final_text = final.text
    result.final_validation = final.validation
    result.final_rounds = final.rounds
    return result

