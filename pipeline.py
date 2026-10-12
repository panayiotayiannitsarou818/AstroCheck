"""v17: πλήρης αυτόματη διαδικασία με ένα κουμπί.

Ο χρήστης ανεβάζει ΜΟΝΟ το Astrodienst PDF. Από εκεί και πέρα:

    ανάλυση 12 Οίκων → έλεγχος → (διόρθωση μέχρι να εγκριθεί)
    → τελικό έντυπο πελάτη → έλεγχος → (διόρθωση μέχρι να εγκριθεί)

Το τελικό έντυπο ξεκινά ΜΟΝΟ αν εγκριθεί η ανάλυση, γιατί η Δεσμευτική Εντολή
Τελικής Αναδιατύπωσης απαιτεί ως πηγή ελεγμένη ανάλυση.

Το module δεν εξαρτάται από το Streamlit, ώστε να ελέγχεται με tests.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from generator import (
    DEFAULT_MAX_ROUNDS,
    REWRITE_REVISION_TEMPLATE,
    Round,
    build_rewrite_prompt,
    completer,
    generate_validated,
)
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
    on_round: Optional[Callable[[str, Round], None]] = None,
    complete: Optional[Callable[[str, str, str], str]] = None,
    validate_analysis_fn: Callable = validate_analysis,
    validate_rewrite_fn: Callable = validate_rewrite,
) -> PipelineResult:
    """Ανάλυση και τελικό έντυπο, το καθένα με κύκλο διόρθωσης μέχρι να εγκριθεί.

    `on_round(στάδιο, Round)` ενημερώνει την οθόνη μετά από κάθε γύρο.
    `complete`, `validate_*_fn`: αντικαθίστανται μόνο στα tests.
    """
    complete = complete or completer(provider)
    result = PipelineResult()
    name = chart.name if getattr(chart, "name", "") else "[ΟΝΟΜΑ]"

    def _report(stage):
        return (lambda r: on_round(stage, r)) if on_round else None

    # 1. Ανάλυση των 12 Οίκων
    analysis_prompt = build_master_prompt(
        chart, personal, language, instructions_text, style_text, instructions_name, style_name
    )
    analysis = generate_validated(
        api_key,
        analysis_prompt,
        validate=lambda t: validate_analysis_fn(chart, t, personal),
        model=model,
        max_rounds=max_rounds,
        on_round=_report(STAGE_ANALYSIS),
        complete=complete,
    )
    result.analysis_text = analysis.text
    result.analysis_validation = analysis.validation
    result.analysis_rounds = analysis.rounds
    if not analysis.ok:
        return result

    # 2. Τελικό έντυπο πελάτη, με πηγή την ΕΓΚΕΚΡΙΜΕΝΗ ανάλυση
    rewrite_prompt = build_rewrite_prompt(
        rewrite_command_text,
        analysis.text,
        name,
        rewrite_language_block(name, language, analysis.text),
    )
    final = generate_validated(
        api_key,
        rewrite_prompt,
        validate=lambda t: validate_rewrite_fn(chart, analysis.text, t, personal),
        model=model,
        max_rounds=max_rounds,
        on_round=_report(STAGE_REWRITE),
        complete=complete,
        revision_template=REWRITE_REVISION_TEMPLATE,
    )
    result.final_text = final.text
    result.final_validation = final.validation
    result.final_rounds = final.rounds
    return result
