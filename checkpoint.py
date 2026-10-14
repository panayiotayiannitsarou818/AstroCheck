"""v19.6: «συνέχεια από εκεί που σταμάτησε» — καθαρή λογική, χωρίς Streamlit.

Η πρόοδος κρατιέται ΜΟΝΟ στη συνεδρία (λεξικό στο session_state) και
ενημερώνεται αμέσως κάθε φορά που βελτιώνεται το καλύτερο κείμενο ενός σταδίου.
Κάθε κείμενο θυμάται τις ρυθμίσεις από τις οποίες προήλθε· αν αλλάξουν
(γλώσσα, οδηγίες, οδηγός ύφους, επιλογές απορρήτου, εντολή αναδιατύπωσης), δεν
ξαναχρησιμοποιείται.
"""

from __future__ import annotations

from case_state import fingerprint

STAGE_ANALYSIS = "Ανάλυση"
STAGE_REWRITE = "Τελικό έντυπο"


def chart_key(chart) -> str:
    """v19.7: η ταυτότητα περιλαμβάνει και τα ΑΣΤΡΟΛΟΓΙΚΑ δεδομένα (πλανήτες,
    ακμές, όψεις): ίδια στοιχεία γέννησης με διαφορετικές θέσεις = άλλος χάρτης."""
    data = "\x1f".join(
        [
            str(chart.name), str(chart.date), str(chart.time), str(chart.place), str(chart.house_system),
            repr(list(getattr(chart, "points", []) or [])),
            repr(list(getattr(chart, "cusps", []) or [])),
            repr(list(getattr(chart, "aspects", []) or [])),
        ]
    )
    return fingerprint(data) or ""


def analysis_signature(language, instructions_text, style_text, chart_shared) -> str:
    c = chart_shared
    return fingerprint(
        "\x1f".join([str(language), instructions_text or "", style_text or "", c.name, c.date, c.time, c.place])
    ) or ""


def rewrite_signature(analysis_sig: str, language, command_text: str) -> str:
    return fingerprint("\x1f".join([analysis_sig or "", str(language), command_text or ""])) or ""


def update(cp: dict | None, key: str, stage: str, text: str, ok: bool, analysis_sig: str, final_sig: str) -> dict:
    """Νέο λεξικό προόδου μετά από βελτίωση του κειμένου ενός σταδίου."""
    cp = dict(cp) if cp and cp.get("key") == key else {"key": key, "done": False}
    if not text:
        return cp
    if stage == STAGE_ANALYSIS:
        # v19.7: άλλο κείμενο Ή άλλες ρυθμίσεις (ακόμη και με ίδιο κείμενο) -> το
        # παλιό έντυπο και η ένδειξη ολοκλήρωσης ακυρώνονται
        if cp.get("analysis") != text or cp.get("analysis_sig") != analysis_sig:
            for k in ("final", "final_ok", "final_sig", "final_for"):
                cp.pop(k, None)
        cp.update(analysis=text, analysis_ok=bool(ok), analysis_sig=analysis_sig)
    else:
        cp.update(final=text, final_ok=bool(ok), final_sig=final_sig, final_for=fingerprint(cp.get("analysis", "")))
    cp["done"] = bool(
        cp.get("analysis_ok")
        and cp.get("final_ok")
        and cp.get("final_for") == fingerprint(cp.get("analysis", ""))
    )
    return cp


def resume_texts(cp: dict | None, key: str, analysis_sig: str, final_sig: str) -> tuple[str, str]:
    """(ανάλυση, έντυπο) προς συνέχεια — μόνο από τον ίδιο χάρτη και τις ίδιες ρυθμίσεις."""
    if not cp or cp.get("key") != key or not cp.get("analysis") or cp.get("analysis_sig") != analysis_sig:
        return "", ""
    final = cp.get("final", "")
    if not final or cp.get("final_sig") != final_sig or cp.get("final_for") != fingerprint(cp["analysis"]):
        final = ""
    return cp["analysis"], final


def resumable(cp: dict | None, key: str) -> bool:
    return bool(cp and cp.get("key") == key and cp.get("analysis") and not cp.get("done"))
