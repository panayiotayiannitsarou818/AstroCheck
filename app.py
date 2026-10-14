import dataclasses
import re
import streamlit as st
import pandas as pd
from pathlib import Path
from prompts import build_master_prompt
from pipeline import STAGE_ANALYSIS, STAGE_REWRITE, run_full_pipeline
from docx_builder import build_audit_docx, build_analysis_docx
from generator import (
    DEFAULT_EUR_PER_USD,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_STALL_ROUNDS,
    MAX_CONSECUTIVE_FAILURES,
    PermanentAPIError,
    Usage,
    price_for,
    STOP_BUDGET,
    STOP_FAILURES,
    STOP_REVIEW,
    STOP_ROUNDS,
    STOP_STALLED,
    cost_limit_from,
    max_rounds_from,
    stall_rounds_from,
    effort_from,
    DEFAULT_MODELS,
    PROVIDER_SETTINGS,
    PROVIDERS,
    REWRITE_REVISION_TEMPLATE,
    build_rewrite_prompt,
    completer,
    generate_validated,
)
from reference_loader import (
    docx_text,
    load_default_references,
)
from content_review import KIND_ANALYSIS, KIND_REWRITE, REVIEW_EFFORT, review_model_for, with_content_review
from progress import KEEP_PAGE_OPEN, ProgressTracker, TimingStore, range_text
from progress import STAGE_ANALYSIS as P_ANALYSIS, STAGE_REWRITE as P_REWRITE
import checkpoint as CP
from validator import validate_analysis, validate_rewrite
from case_state import fingerprint, forget_stale_results, handle_pdf_upload, reset_case_state
from ui_texts import (
    APP_VERSION,
    analysis_paste_message,
    language_notes,
    rewrite_language_block,
    rewrite_paste_message,
)

st.set_page_config(page_title="AstroCheck Pro", page_icon="✦", layout="wide")
# Στυλ της εφαρμογής. Γράφεται ένας κανόνας ανά γραμμή για να διαβάζεται,
# αλλά οι γραμμές ενώνονται σε ΕΝΑ ενιαίο κείμενο -- ακριβώς όπως πριν --
# ώστε το Markdown του Streamlit να μην το ερμηνεύσει ως μπλοκ κώδικα.
APP_CSS = (
    "<style>\n"
    ".stApp{background:#f5f7f3}"
    ".block-container{max-width:1180px;padding-top:2rem}"
    # Πάνω πλαίσιο με τον τίτλο
    ".hero{background:#19332f;color:white;border-radius:22px;padding:30px 34px;margin-bottom:18px}"
    ".hero h1{margin:0 0 8px;font-family:Georgia;font-size:42px}"
    ".hero p{color:#dce8e2}"
    # Πράσινο (επιτυχία) και πορτοκαλί (προειδοποίηση) πλαίσιο μηνύματος
    ".ok{padding:14px 16px;background:#e5f2e7;border-left:5px solid #39704c;border-radius:8px}"
    ".warn{padding:14px 16px;background:#fff1dd;border-left:5px solid #b7791f;border-radius:8px}"
    'div[data-testid="stMetric"]{background:white;border:1px solid #dce4df;padding:12px;border-radius:12px}'
    # Κατάσταση βημάτων
    ".step-done{color:#2f6b46;font-weight:600}"
    ".step-pending{color:#8a8f8c}"
    ".step-warn{color:#b7791f;font-weight:600}"
    "</style>"
)
st.markdown(APP_CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="hero"><h1>AstroCheck Pro</h1><p>Ανέβασε το Astrodienst PDF, δημιούργησε την ανάλυση και κατέβασε το τελικό Word.</p></div>',
    unsafe_allow_html=True,
)

if "chart" not in st.session_state:
    st.session_state.chart = None
if "analysis" not in st.session_state:
    st.session_state.analysis = ""
if "validation" not in st.session_state:
    st.session_state.validation = None
if "analysis_docx_bytes" not in st.session_state:
    st.session_state.analysis_docx_bytes = None
if "analysis_docx_name" not in st.session_state:
    st.session_state.analysis_docx_name = ""
if "rewrite_validation" not in st.session_state:
    st.session_state.rewrite_validation = None
if "uploader_gen" not in st.session_state:
    st.session_state.uploader_gen = (
        0  # αλλάζει τα keys των uploaders ώστε το "Νέα ανάλυση" να τους αδειάζει πραγματικά
    )

# Τα tabs του Streamlit δεν άλλαζαν αυτόματα μετά την ανάγνωση ενός PDF.
# Έτσι ο χρήστης έβλεπε ότι ο χάρτης είχε φορτωθεί, αλλά παρέμενε στην
# «1 · Αρχεία» χωρίς εμφανή τρόπο συνέχειας.  Το προσωρινό request γράφεται
# από τα κουμπιά και εφαρμόζεται ΠΡΙΝ δημιουργηθεί το widget των tabs.
if st.session_state.get("_requested_main_tab"):
    st.session_state.main_tab = st.session_state.pop("_requested_main_tab")


def _current_upload_bytes(prefix: str):
    upload = st.session_state.get(f"{prefix}_{st.session_state.uploader_gen}")
    return upload.getvalue() if upload is not None else None


# Αν το ανεβασμένο Word άλλαξε ή αφαιρέθηκε μετά τον έλεγχο, το παλιό
# αποτέλεσμα και το παλιό αρχείο λήψης ακυρώνονται ΠΡΙΝ εμφανιστεί οτιδήποτε
# (και η λίστα βημάτων στο πλάι). Βλ. case_state.forget_stale_results.
_stale = forget_stale_results(
    analysis_upload=_current_upload_bytes("analysis_docx"),
    rewrite_upload=_current_upload_bytes("rewrite_docx"),
)


def _error_with_details(validation, suffix: str) -> None:
    """Κόκκινο μήνυμα που περιλαμβάνει ΑΝΑΛΥΤΙΚΑ κάθε σφάλμα (σημείο,
    ενότητα και ακριβή πρόταση), συν έτοιμο κείμενο για επικόλληση στο
    ChatGPT/Claude ώστε η διόρθωση να είναι στοχευμένη."""
    lines = validation.details_lines()
    body = validation.summary() + " " + suffix
    if lines:
        body += "\n\n**Αναλυτικά:**\n" + "\n".join(f"- {l}" for l in lines)
    st.error(body)
    if lines:
        with st.expander("📋 Κείμενο διόρθωσης για επικόλληση στο ChatGPT/Claude"):
            st.code(
                "Ο έλεγχος AstroCheck εντόπισε τα εξής. Διόρθωσε ΜΟΝΟ αυτά τα σημεία, "
                "χωρίς να αλλάξεις όψεις, orb, βαρύτητες ή ενότητες, και παράδωσε ξανά "
                "ολόκληρο το Word:\n" + "\n".join(f"- {l}" for l in lines),
                language=None,
            )


TAB_ANALYSIS = "2 · Ανάλυση & έλεγχος"


def _analysis_result_panel(source: str, chart_name: str) -> None:
    """Αποτέλεσμα ελέγχου ΑΚΡΙΒΩΣ κάτω από το κουμπί που το προκάλεσε.

    Αντικαθιστά την πρώην καρτέλα «3 · Τεχνικό Word»: αν ο έλεγχος περάσει,
    η λήψη εμφανίζεται εδώ· αν όχι, εμφανίζονται αναλυτικά τα σφάλματα και
    η λήψη μένει κλειδωμένη. `source` = 'api' | 'docx' | 'paste'.
    """
    if st.session_state.get("analysis_source") != source or not st.session_state.analysis:
        return
    validation = st.session_state.validation
    if validation is None:
        return
    if validation.ok:
        st.success(validation.summary())
        if source == "docx" and st.session_state.analysis_docx_bytes:
            final_doc = st.session_state.analysis_docx_bytes
            final_name = st.session_state.analysis_docx_name or "Pliris_Astrologiki_Analysi.docx"
        else:
            final_doc = build_analysis_docx(chart_name, st.session_state.analysis)
            final_name = "Pliris_Astrologiki_Analysi.docx"
        st.download_button(
            "⬇️ Λήψη ελεγμένης πλήρους ανάλυσης (Word)",
            final_doc,
            file_name=final_name,
            type="primary",
            width="stretch",
            key=f"download_analysis_{source}",
        )
        st.button(
            "Συνέχεια στην Τελική αναδιατύπωση →",
            width="stretch",
            on_click=_request_main_tab,
            args=("3 · Τελική αναδιατύπωση",),
            key=f"to_rewrite_{source}",
        )
    else:
        suffix = (
            "Το Word απορρίφθηκε και η λήψη παραμένει κλειδωμένη."
            if source == "docx"
            else "Η λήψη παραμένει κλειδωμένη."
        )
        _error_with_details(validation, suffix)
    with st.expander("Προεπισκόπηση κειμένου ανάλυσης"):
        st.text_area(
            "Κείμενο ανάλυσης",
            st.session_state.analysis,
            height=380,
            label_visibility="collapsed",
            key=f"preview_{source}",
        )


BIRTH_HIDDEN = "Δεν κοινοποιείται"


def _initials(name: str) -> str:
    """Αρχικά από το όνομα του PDF, π.χ. «Elena Kakouli» → «E.K.».
    Αν το «όνομα» είναι στην πραγματικότητα όνομα αρχείου (δεν υπήρχε όνομα
    στο PDF), επιστρέφεται το ουδέτερο «Πελάτης»."""
    name = (name or "").strip()
    if not name or "_" in name or re.search(r"\d", name):
        return "Πελάτης"
    words = re.findall(r"[^\W\d_]+", name)
    return "".join(w[0].upper() + "." for w in words[:3]) or "Πελάτης"


def _shared_chart(chart):
    """Ο χάρτης όπως θα φύγει προς ChatGPT/Claude/OpenAI και στα έγγραφα.

    Απόρρητο εξ ορισμού, χωρίς ερωτήσεις: το όνομα αντικαθίσταται ΠΑΝΤΑ με
    τα αρχικά και τα γενέθλια στοιχεία αποκρύπτονται, εκτός αν ο χρήστης
    επιλέξει ρητά να εμφανίζονται. Οι αστρολογικές θέσεις, οι Οίκοι και οι
    όψεις μένουν ΑΚΡΙΒΩΣ ίδια· ο αρχικός χάρτης δεν τροποποιείται.
    """
    if chart is None:
        return None
    name = _initials(chart.name)
    if st.session_state.get("hide_birth", True):
        return dataclasses.replace(
            chart, name=name, date=BIRTH_HIDDEN, time=BIRTH_HIDDEN, place=BIRTH_HIDDEN
        )
    return dataclasses.replace(chart, name=name)


def _privacy_panel(original) -> None:
    """Ενημέρωση απορρήτου. Δεν χρειάζεται καμία ενέργεια: η προστασία
    εφαρμόζεται αυτόματα."""
    if "hide_birth" not in st.session_state:
        st.session_state.hide_birth = True
    with st.expander("🔒 Απόρρητο πελάτη (εφαρμόζεται αυτόματα)", expanded=False):
        st.markdown(
            f"Σε ό,τι στέλνεται στο ChatGPT, στο Claude ή στην OpenAI και στα έγγραφα, το όνομα "
            f"αντικαθίσταται αυτόματα με τα αρχικά **{_initials(original.name)}**. Αν θέλεις "
            f"το πραγματικό όνομα στο τελικό έντυπο του πελάτη, πρόσθεσέ το στο Word πριν το "
            f"παραδώσεις. Οι θέσεις, οι Οίκοι και οι όψεις μένουν πάντα πλήρεις."
        )
        st.checkbox(
            "Απόκρυψη ημερομηνίας, ώρας και τόπου γέννησης",
            key="hide_birth",
            help=f"Προεπιλογή: ενεργό. Στη θέση τους γράφεται «{BIRTH_HIDDEN}». Η ανάλυση "
            "δεν επηρεάζεται, γιατί τα αστρολογικά δεδομένα έχουν ήδη υπολογιστεί από το PDF.",
        )


def _secret(name: str) -> str:
    """Τιμή από τα Streamlit secrets, ή κενό αν δεν έχουν οριστεί."""
    try:
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def _max_rounds() -> int:
    """v16: όριο ασφαλείας του κύκλου «μέχρι να εγκριθεί» (Secrets: AUTO_MAX_ROUNDS)."""
    value = _secret("AUTO_MAX_ROUNDS")
    return max_rounds_from(DEFAULT_MAX_ROUNDS if value in (None, "") else value)


def _effort() -> str:
    """v17.1: επίπεδο προσπάθειας του Claude (Secrets: ANTHROPIC_EFFORT, προεπιλογή high)."""
    return effort_from(_secret("ANTHROPIC_EFFORT"))


def _cap_text(cap: int) -> str:
    return "χωρίς όριο γύρων" if cap == 0 else f"όριο ασφαλείας: {cap} γύροι"


def _stall_rounds() -> int:
    """v18: διακοπή όταν δεν υπάρχει πρόοδος (Secrets: AUTO_STALL_ROUNDS)."""
    return stall_rounds_from(_secret("AUTO_STALL_ROUNDS") or DEFAULT_STALL_ROUNDS)


def _max_cost():
    """v18: προαιρετικό όριο κόστους ανά πελάτη σε $ (Secrets: AUTO_MAX_COST_USD)."""
    return cost_limit_from(_secret("AUTO_MAX_COST_USD"))


def _eur_rate() -> float:
    try:
        return float(_secret("EUR_PER_USD").replace(",", ".")) or DEFAULT_EUR_PER_USD
    except ValueError:
        return DEFAULT_EUR_PER_USD


def _price_override():
    """v19: τιμή για μοντέλο εκτός πίνακα (Secrets: PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK)."""
    try:
        inp = float(_secret("PRICE_INPUT_PER_MTOK").replace(",", "."))
        out = float(_secret("PRICE_OUTPUT_PER_MTOK").replace(",", "."))
    except ValueError:
        return None
    return (inp, out) if inp > 0 and out > 0 else None


def _case_usage(model: str) -> Usage:
    """v19: ΕΝΑΣ μετρητής ανά πελάτη, κοινός για την αυτόματη διαδικασία και τις
    καρτέλες 2 και 3. v19.6: δένεται με τον χάρτη, ώστε να ΜΗΝ μηδενίζεται όταν
    ξαναδιαβάζεται το ίδιο PDF (μαζί με τη μισοτελειωμένη εργασία)· μηδενίζεται
    με «Νέα ανάλυση» ή με PDF άλλου χάρτη."""
    chart = st.session_state.get("chart")
    key = _chart_key(chart) if chart is not None else ""
    slot = st.session_state.get("case_usage")
    if not isinstance(slot, dict) or slot.get("key") != key:
        slot = {"key": key, "usage": Usage(model=model)}
        st.session_state.case_usage = slot
    usage = slot["usage"]
    usage.model = model
    usage.price_override = _price_override()
    return usage


def _review_on() -> bool:
    """v19: έλεγχος περιεχομένου με ΤΝ (Secrets: CONTENT_REVIEW = off για απενεργοποίηση)."""
    return _secret("CONTENT_REVIEW").lower() not in ("off", "0", "false", "όχι")


def _with_review(validate, provider, api, model, kind, source=""):
    if not _review_on():
        return validate
    return with_content_review(
        validate,
        completer(provider, REVIEW_EFFORT),
        api,
        review_model_for(provider, model, _secret("REVIEW_MODEL")),
        kind,
        source,
        _case_usage(model),
        _max_cost(),
    )


def _cost_limit_warning(model: str) -> None:
    if _max_cost() and price_for(model, _price_override()) is None:
        st.warning(
            f"Το όριο κόστους δεν μπορεί να εφαρμοστεί: δεν υπάρχει τιμή για το μοντέλο {model}. "
            "Όρισε PRICE_INPUT_PER_MTOK και PRICE_OUTPUT_PER_MTOK στα Secrets."
        )


def _limits_text(cap: int) -> str:
    text = f"{_cap_text(cap)}· διακοπή αν δεν υπάρξει πρόοδος για {_stall_rounds()} γύρους"
    cost = _max_cost()
    if cost:
        text += f"· όριο κόστους {cost:.2f} $".replace(".", ",")
    return text


def _stop_text(reason, cap: int) -> str:
    """Εξήγηση στα ελληνικά για το γιατί σταμάτησε ο κύκλος χωρίς να περάσει."""
    if reason == STOP_STALLED:
        return (
            f"σταμάτησε επειδή για {_stall_rounds()} συνεχόμενους γύρους τα σφάλματα δεν μειώθηκαν "
            "(στασιμότητα) — κρατήθηκε η καλύτερη απόπειρα. Δες τα σφάλματα παρακάτω· μπορείς να "
            "πατήσεις ξανά για νέα προσπάθεια."
        )
    if reason == STOP_BUDGET:
        return "σταμάτησε επειδή έφτασε το όριο κόστους (AUTO_MAX_COST_USD) — κρατήθηκε η καλύτερη απόπειρα."
    if reason == STOP_REVIEW:
        return (
            "πέρασε τους ελέγχους δεδομένων και δομής, αλλά ο έλεγχος περιεχομένου με ΤΝ δεν ολοκληρώθηκε, "
            "οπότε το κείμενο ΔΕΝ θεωρείται ελεγμένο. Πάτα ξανά σε λίγο για νέα προσπάθεια."
        )
    if reason == STOP_FAILURES:
        return (
            f"σταμάτησε μετά από {MAX_CONSECUTIVE_FAILURES} αποτυχημένα αιτήματα στη σειρά "
            "(δίκτυο ή υπερφόρτωση του παρόχου) — δοκίμασε ξανά σε λίγο."
        )
    return f"δεν πέρασε τους ελέγχους ούτε μετά από {cap} γύρους (όριο ασφαλείας) — δες τα σφάλματα παρακάτω."


def _analysis_resume_text(sig: str = "") -> str:
    """v19.5: καρτέλα 2 — συνέχεια από την καλύτερη αυτόματη απόπειρα που δεν
    πέρασε. v19.6: μόνο αν προήλθε από τις ΙΔΙΕΣ ρυθμίσεις (γλώσσα, οδηγίες, απόρρητο)."""
    v = st.session_state.get("validation")
    if (
        st.session_state.get("analysis_source") == "api"
        and st.session_state.get("analysis")
        and v is not None
        and not v.ok
        and st.session_state.get("analysis_sig") == sig
    ):
        return st.session_state.analysis
    return ""


def _rewrite_resume_text(analysis_text: str, sig: str = "") -> str:
    """v19.5: καρτέλα 3 — συνέχεια μόνο αν το έντυπο προήλθε από την ΙΔΙΑ ανάλυση."""
    v = st.session_state.get("rewrite_validation")
    if (
        st.session_state.get("rewrite_source") == "api"
        and st.session_state.get("rewrite_text")
        and st.session_state.get("rewrite_analysis_hash") == fingerprint(analysis_text)
        and v is not None
        and not v.ok
        and st.session_state.get("rewrite_sig") == sig
    ):
        return st.session_state.rewrite_text
    return ""


def _progress_panel(stages):
    """v19.4: μήνυμα «μην κλείσεις τη σελίδα», μπάρα προόδου ανά στάδιο και
    εκτίμηση χρόνου που απομένει. Επιστρέφει (tracker, ενημέρωση(στάδιο, γύρος))."""
    store = TimingStore()
    st.warning(KEEP_PAGE_OPEN)
    tracker = ProgressTracker(store, tuple(stages))
    st.caption(f"{range_text(store, tuple(stages))}. Η εκτίμηση γίνεται πιο ακριβής με κάθε ανάλυση.")
    bar = st.progress(0.02, text=tracker.label())

    def update(stage, rnd):
        tracker.on_round(stage, rnd)
        bar.progress(tracker.fraction(), text=tracker.label())

    def finish():
        tracker.finish()
        bar.progress(1.0, text="Ολοκληρώθηκε.")

    return update, finish


def _show_api_error(e: Exception, provider: str) -> None:
    if isinstance(e, PermanentAPIError):
        st.error(f"Η διαδικασία σταμάτησε αμέσως: {e} (Δεν έγιναν άσκοπες επαναλήψεις.)")
    else:
        st.error(f"Η δημιουργία απέτυχε. Έλεγξε το κλειδί {provider} και δοκίμασε ξανά.")
    cause = e.__cause__ or e
    with st.expander("Τεχνική λεπτομέρεια"):
        st.code(f"{type(cause).__name__}: {str(cause)[:300]}")


def _api_choice(scope: str):
    """Επιλογή μοντέλου (Claude ή OpenAI) και κλειδί API. Επιστρέφει
    (πάροχος, κλειδί, μοντέλο). Κάθε στάδιο (ανάλυση, αναδιατύπωση) έχει δική του επιλογή."""
    choice = st.radio(
        "Μοντέλο που γράφει",
        PROVIDERS,
        horizontal=True,
        key=f"provider_{scope}",
    )
    key_name, model_name, placeholder = PROVIDER_SETTINGS[choice]
    model = _secret(model_name) or DEFAULT_MODELS[choice]
    saved_key = _secret(key_name)
    if saved_key:
        st.caption(f"🔑 Χρησιμοποιείται το κλειδί {choice} από τις ρυθμίσεις της εφαρμογής. Μοντέλο: {model}.")
        return choice, saved_key, model
    st.caption(
        f"Χρειάζεται δικό σου {choice} API key. Δεν αποθηκεύεται πουθενά. "
        f"(Μπορείς να το ορίσεις μόνιμα στα Secrets της εφαρμογής ως {key_name}.) Μοντέλο: {model}."
    )
    api = st.text_input(
        f"{choice} API key",
        type="password",
        label_visibility="collapsed",
        placeholder=placeholder,
        key=f"api_key_{choice}_{scope}",
    )
    return choice, api, model


def _request_main_tab(label: str) -> None:
    st.session_state._requested_main_tab = label


# reset_case_state()/handle_pdf_upload() ζουν στο case_state.py -- εξήχθησαν
# από εδώ ώστε να είναι ελέγξιμα με απλά unit tests (βλ. tests/test_case_state.py),
# αφού το streamlit.testing δεν υποστηρίζει προσομοίωση st.file_uploader.

try:
    default_instructions_text, default_style_text = load_default_references()
except Exception as e:
    st.error(f"Σφάλμα ενσωματωμένων αρχείων: {e}")
    st.stop()

chart_ready = st.session_state.chart is not None
analysis_ok = (
    bool(st.session_state.analysis)
    and st.session_state.validation is not None
    and st.session_state.validation.ok
)
analysis_warn = (
    bool(st.session_state.analysis)
    and st.session_state.validation is not None
    and not st.session_state.validation.ok
)

with st.sidebar:
    st.header("Πρόοδος")

    def _step(label, done, warn=False, optional_note=None):
        if warn:
            st.markdown(f'<span class="step-warn">⚠ {label}</span>', unsafe_allow_html=True)
        elif done:
            st.markdown(f'<span class="step-done">✓ {label}</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="step-pending">○ {label}</span>', unsafe_allow_html=True)
            if optional_note:
                st.caption(optional_note)

    _step("1. PDF και αρχεία", chart_ready)
    _step("2. Δημιουργία & έλεγχος πληρότητας", analysis_ok, warn=analysis_warn)
    _step(
        "3. Τελική αναδιατύπωση",
        bool(st.session_state.rewrite_validation and st.session_state.rewrite_validation.ok),
    )

    st.divider()
    st.caption("Τα δεδομένα επεξεργάζονται στη συνεδρία και δεν αποθηκεύονται από την εφαρμογή.")
    st.caption(f"Έκδοση AstroCheck: {APP_VERSION}")
    if st.button(
        "🔄 Νέα ανάλυση (καθαρισμός όλων)",
        width="stretch",
        help="Καθαρίζει τον χάρτη και τις αναλύσεις, ώστε να ξεκινήσεις με άλλο άτομο.",
    ):
        st.session_state.chart = None
        st.session_state.uploader_gen += 1  # αναγκάζει τους file_uploader να ξαναγίνουν "άδειοι"
        reset_case_state()
        st.session_state.pop("checkpoint", None)  # v19.5: και η μισοτελειωμένη εργασία
        st.session_state.pop("case_usage", None)  # v19.6: και ο μετρητής κόστους του πελάτη
        st.rerun()

REWRITE_COMMAND_PATH = Path(__file__).resolve().parent / "Desmeftiki_Entoli_Telikis_Anadiatyposis_v9.docx"


def _chart_key(chart) -> str:
    return CP.chart_key(chart)


analysis_signature = CP.analysis_signature
rewrite_signature = CP.rewrite_signature


def _checkpoint():
    """v19.5–19.6: η πρόοδος για τον ΤΡΕΧΟΝΤΑ χάρτη (μόνο στη συνεδρία· βλ. checkpoint.py)."""
    cp = st.session_state.get("checkpoint")
    chart = st.session_state.get("chart")
    if not cp or chart is None or cp.get("key") != _chart_key(chart):
        return None
    return cp


def _checkpoint_update(stage: str, text: str, ok: bool, analysis_sig: str, final_sig: str) -> None:
    chart = st.session_state.get("chart")
    if chart is None:
        return
    st.session_state.checkpoint = CP.update(
        st.session_state.get("checkpoint"), _chart_key(chart), stage, text, ok, analysis_sig, final_sig
    )


def _resume_texts(analysis_sig: str, final_sig: str):
    chart = st.session_state.get("chart")
    if chart is None:
        return "", ""
    return CP.resume_texts(st.session_state.get("checkpoint"), _chart_key(chart), analysis_sig, final_sig)


def _resumable() -> bool:
    chart = st.session_state.get("chart")
    return chart is not None and CP.resumable(st.session_state.get("checkpoint"), _chart_key(chart))


def _store_pipeline_result(result, chart_shared, analysis_sig: str = "", final_sig: str = "") -> None:
    """Τα αποτελέσματα στα ΙΔΙΑ κλειδιά με τις καρτέλες 2 και 3.
    v19.7: κάθε υπογραφή ρυθμίσεων αποθηκεύεται ΜΟΝΟ μαζί με το κείμενο που
    πραγματικά δημιουργήθηκε με αυτές -- ποτέ πριν (ένα παλιό κείμενο δεν
    «αποκτά» νέες ρυθμίσεις αν η νέα εκτέλεση αποτύχει πριν γράψει κάτι)."""
    if result.analysis_text:
        st.session_state.analysis_sig = analysis_sig
        st.session_state.analysis = result.analysis_text
        st.session_state.validation = result.analysis_validation
        st.session_state.analysis_source = "api"
        st.session_state.analysis_docx_bytes = None
        st.session_state.analysis_docx_name = ""
    if result.final_text:
        st.session_state.rewrite_sig = final_sig
        st.session_state.rewrite_validation = result.final_validation
        st.session_state.rewrite_docx_bytes = build_analysis_docx(chart_shared.name, result.final_text)
        st.session_state.rewrite_docx_name = "Teliki_Analysi.docx"
        st.session_state.rewrite_docx_hash = None
        st.session_state.rewrite_analysis_hash = fingerprint(result.analysis_text)
        st.session_state.rewrite_source = "api"
        st.session_state.rewrite_text = result.final_text
    cp = _checkpoint()
    if cp is not None and getattr(result, "ok", False):
        cp["done"] = True


def _run_full_pipeline_ui(provider, api, model, language, instructions_upload, style_upload, fresh=False) -> None:
    """v17: ανάλυση → έλεγχος → τελικό έντυπο → έλεγχος, με ενημέρωση ανά γύρο.
    v19.5: αν υπάρχει διακοπείσα εκτέλεση για τον ίδιο χάρτη, ΣΥΝΕΧΙΖΕΙ από εκεί
    (εκτός αν ζητηθεί `fresh`)."""
    chart_shared = _shared_chart(st.session_state.chart)
    personal = {"Όνομα": chart_shared.name}
    ins_text = docx_text(instructions_upload.getvalue()) if instructions_upload else default_instructions_text
    sty_text = docx_text(style_upload.getvalue()) if style_upload else default_style_text
    ins_name = instructions_upload.name if instructions_upload else "Ενσωματωμένες οδηγίες v6"
    sty_name = style_upload.name if style_upload else "Ενσωματωμένος καθαρός οδηγός ύφους"
    st.session_state.language = language
    command_text = docx_text(REWRITE_COMMAND_PATH.read_bytes())
    a_sig = analysis_signature(language, ins_text, sty_text, chart_shared)
    f_sig = rewrite_signature(a_sig, language, command_text)
    if fresh:
        st.session_state.pop("checkpoint", None)
    resume_a, resume_f = _resume_texts(a_sig, f_sig)
    if resume_a:
        st.info("▶️ Συνέχεια από εκεί που είχε σταματήσει — δεν ξαναγράφεται η ανάλυση από την αρχή.")
    elif _resumable() and not fresh:
        st.info(
            "Οι ρυθμίσεις άλλαξαν από την προηγούμενη προσπάθεια (γλώσσα, οδηγίες ή επιλογές απορρήτου), "
            "οπότε η ανάλυση γράφεται από την αρχή με τις νέες ρυθμίσεις."
        )
    progress_update, progress_finish = _progress_panel((P_ANALYSIS, P_REWRITE))
    with st.status("Λεπτομέρειες γύρων", expanded=False) as status:

        def _on_round(stage, r):
            progress_update(stage, r)
            status.write(
                f"{'✓' if r.ok else '✗'} {stage} — γύρος {r.number} ({r.kind}): "
                + (r.summary if r.kind == "γύρος ποιότητας" else "πέρασε τους ελέγχους." if r.ok else f"{r.error_count} σφάλματα — διορθώνεται…")
            )

        try:
            result = run_full_pipeline(
                chart=chart_shared,
                personal=personal,
                language=language,
                instructions_text=ins_text,
                style_text=sty_text,
                instructions_name=ins_name,
                style_name=sty_name,
                rewrite_command_text=command_text,
                api_key=api,
                provider=provider,
                model=model,
                max_rounds=_max_rounds(),
                effort=_effort(),
                stall_rounds=_stall_rounds(),
                max_cost_usd=_max_cost(),
                on_round=_on_round,
                usage=_case_usage(model),
                content_review=_review_on(),
                review_model=_secret("REVIEW_MODEL"),
                resume_analysis=resume_a,
                resume_final=resume_f,
                on_progress=lambda stage, text, ok: _checkpoint_update(stage, text, ok, a_sig, f_sig),
            )
        except Exception as e:
            progress_finish()
            status.update(label="Η αυτόματη διαδικασία διακόπηκε.", state="error")
            partial = getattr(e, "result", None)
            if partial is not None:
                _store_pipeline_result(partial, chart_shared, a_sig, f_sig)  # η πρόοδος ΔΕΝ χάνεται
            cause = e.__cause__ or e
            st.session_state.auto_result = {
                "error": f"{type(cause).__name__}: {str(cause)[:300]}",
                "permanent": str(e) if isinstance(e, PermanentAPIError) else "",
                "provider": provider,
                "saved": _resumable(),
                "name": chart_shared.name,
            }
            return
        progress_finish()
        _store_pipeline_result(result, chart_shared, a_sig, f_sig)
        st.session_state.auto_result = {
            "ok": result.ok,
            "stopped_at": result.stopped_at,
            "analysis_rounds": len(result.analysis_rounds),
            "final_rounds": len(result.final_rounds),
            "name": chart_shared.name,
            "stop_reason": result.stop_reason,
            "cap": _max_rounds(),
            "usage": result.usage.describe(_eur_rate()) if result.usage else "",
            "review": _review_on(),
            "saved": _resumable(),
        }
        status.update(
            label="✓ Ολοκληρώθηκε: η ανάλυση και το τελικό έντυπο πέρασαν τους ελέγχους δεδομένων, δομής και ασφαλούς γλώσσας."
            if result.ok
            else f"Η διαδικασία σταμάτησε στο στάδιο «{result.stopped_at}» χωρίς να περάσει τους ελέγχους.",
            state="complete" if result.ok else "error",
        )


def _auto_result_panel() -> None:
    """Αποτέλεσμα της πλήρους αυτόματης διαδικασίας, με τις λήψεις, στην καρτέλα 1."""
    res = st.session_state.get("auto_result")
    if not res:
        return
    with st.container(border=True):
        st.markdown("#### Αποτέλεσμα αυτόματης διαδικασίας")
        if res.get("error"):
            if res.get("permanent"):
                st.error(f"Η αυτόματη διαδικασία σταμάτησε αμέσως: {res['permanent']}")
            else:
                st.error(f"Η αυτόματη διαδικασία διακόπηκε. Έλεγξε το κλειδί {res.get('provider')} και δοκίμασε ξανά.")
            st.caption("Τεχνική λεπτομέρεια: " + res["error"])
            if res.get("saved"):
                st.info(
                    "💾 Η πρόοδος κρατήθηκε. Διόρθωσε την αιτία (π.χ. πρόσθεσε υπόλοιπο στο Claude Console) "
                    "και πάτα «▶️ Συνέχεια από εκεί που σταμάτησε» — δεν ξεκινά από την αρχή. "
                    "Μην κλείσεις τη σελίδα, γιατί η πρόοδος υπάρχει μόνο σε αυτή τη συνεδρία."
                )
            return
        if res.get("usage"):
            st.caption("💶 Κατανάλωση αυτού του πελάτη: " + res["usage"])
        analysis_ok = bool(st.session_state.validation and st.session_state.validation.ok)
        final = st.session_state.get("rewrite_validation")
        if analysis_ok:
            st.success(f"✓ Η ανάλυση πέρασε τους ελέγχους δεδομένων, δομής και ασφαλούς γλώσσας ({res['analysis_rounds']} γύροι).")
            st.download_button(
                "⬇️ Λήψη ελεγμένης πλήρους ανάλυσης (Word)",
                build_analysis_docx(res["name"], st.session_state.analysis),
                file_name="Pliris_Astrologiki_Analysi.docx",
                width="stretch",
                key="auto_download_analysis",
            )
        if final is not None and final.ok and st.session_state.get("rewrite_docx_bytes"):
            st.success(f"✓ Το τελικό έντυπο του πελάτη πέρασε τους ελέγχους δεδομένων, δομής και ασφαλούς γλώσσας ({res['final_rounds']} γύροι).")
            for note in getattr(final, "warnings", []):
                st.warning(note)
            st.download_button(
                "⬇️ Λήψη τελικού εντύπου πελάτη (Word)",
                st.session_state.rewrite_docx_bytes,
                file_name=st.session_state.get("rewrite_docx_name") or "Teliki_Analysi.docx",
                type="primary",
                width="stretch",
                key="auto_download_final",
            )
            st.caption("Ο έλεγχος δεν κρίνει αν διατηρήθηκε όλο το νόημα· διάβασε το έντυπο πριν το παραδώσεις.")
        if res.get("stopped_at"):
            failed = st.session_state.validation if res["stopped_at"] == STAGE_ANALYSIS else final
            st.error(
                f"Το στάδιο «{res['stopped_at']}» "
                + _stop_text(res.get("stop_reason"), res.get("cap", _max_rounds()))
                + (
                    " Η πρόοδος κρατήθηκε: πάτα «▶️ Συνέχεια από εκεί που σταμάτησε»."
                    if res.get("saved")
                    else " Μπορείς να συνεχίσεις από την αντίστοιχη καρτέλα."
                )
            )
            if failed is not None:
                with st.expander("Σφάλματα", expanded=True):
                    for line in failed.details_lines():
                        st.write("•", line)


MAIN_TABS = ["1 · Αρχεία", TAB_ANALYSIS, "3 · Τελική αναδιατύπωση"]
# Μια συνεδρία που είχε ανοιχτή καρτέλα με παλιό όνομα (π.χ. «3 · Τεχνικό Word»,
# που καταργήθηκε) επιστρέφει με ασφάλεια στην πρώτη καρτέλα.
if st.session_state.get("main_tab") not in (None, *MAIN_TABS):
    st.session_state.main_tab = "1 · Αρχεία"
# on_change="rerun": απαραίτητο ώστε η ενεργή καρτέλα να παρακολουθείται στο
# st.session_state.main_tab. Με την προεπιλογή ("ignore") η καρτέλα ΔΕΝ
# παρακολουθείται, οπότε τα κουμπιά «Συνέχεια στην …» άλλαζαν την τιμή χωρίς
# κανένα αποτέλεσμα. Όλες οι καρτέλες εξακολουθούν να εκτελούνται σε κάθε rerun.
# Η προεπιλογή δίνεται μόνο στην πρώτη εμφάνιση, για να μη συγκρούεται με την
# τιμή που ορίζουν τα κουμπιά μέσω session_state.
tab1, tab4, tab6 = st.tabs(
    MAIN_TABS,
    key="main_tab",
    on_change="rerun",
    default=None if st.session_state.get("main_tab") else "1 · Αρχεία",
)

with tab1:
    st.subheader("Ανέβασε μόνο το νέο PDF")
    st.success("✓ Οι οδηγίες και ο οδηγός ύφους είναι ενσωματωμένα.")
    pdf = st.file_uploader(
        "Νέο Astrodienst Data Sheet", type=["pdf"], key=f"pdf_{st.session_state.uploader_gen}"
    )
    with st.expander("Προχωρημένα: προαιρετική προσωρινή αντικατάσταση"):
        instructions = st.file_uploader(
            "Νεότερες οδηγίες", type=["docx"], key=f"instructions_{st.session_state.uploader_gen}"
        )
        style = st.file_uploader(
            "Νεότερο πρότυπο ύφους", type=["docx"], key=f"style_{st.session_state.uploader_gen}"
        )
    # v17: ΠΛΗΡΗΣ ΑΥΤΟΜΑΤΗ ΔΙΑΔΙΚΑΣΙΑ — ο χρήστης ανεβάζει μόνο το PDF.
    with st.container(border=True):
        auto_full = st.toggle(
            "🤖 Πλήρης αυτόματη διαδικασία (ανεβάζεις μόνο το PDF)",
            value=True,
            key="auto_full",
            help="Μετά την ανάγνωση του PDF, η εφαρμογή δημιουργεί την ανάλυση, την ελέγχει, γράφει "
            "το τελικό έντυπο του πελάτη και το ελέγχει — με διόρθωση μέχρι να περάσει τους ελέγχους το καθένα.",
        )
        if auto_full:
            auto_provider, auto_api, auto_model = _api_choice("full")
            auto_language = st.selectbox(
                "Γλώσσα τελικού εντύπου πελάτη", ["Ελληνικά", "Αγγλικά"], key="auto_language"
            )
            st.caption(
                "Μετά το «Ανάγνωση και έλεγχος PDF» όλα γίνονται αυτόματα: ανάλυση → έλεγχος → "
                f"τελικό έντυπο → έλεγχος, μέχρι να περάσει τους ελέγχους το καθένα ({_limits_text(_max_rounds())}). "
                f"{range_text(TimingStore())}· **μην κλείσεις και μην ανανεώσεις τη σελίδα** μέχρι να τελειώσει."
            )
            if not auto_api:
                st.warning("Για την αυτόματη διαδικασία χρειάζεται κλειδί API (ή όρισέ το στα Secrets).")
            _cost_limit_warning(auto_model)
    if pdf and st.button("Ανάγνωση και έλεγχος PDF", type="primary", width="stretch"):
        with st.spinner("Διαβάζεται το PDF…"):
            ok, new_chart, err = handle_pdf_upload(pdf.getvalue(), pdf.name)
            # Η λογική "διάβασε -> καθάρισε προηγούμενη περίπτωση -> bump
            # uploader_gen -> αποθήκευσε chart" ζει στο case_state.handle_pdf_upload
            # (βλ. εκεί το γιατί) και ήδη γράφει κατευθείαν στο πραγματικό
            # st.session_state (δεν περάσαμε state=... εδώ) -- εδώ μένει μόνο
            # η παρουσίαση.
            if ok and auto_full and auto_api:
                st.session_state.pop("auto_result", None)
            elif ok:
                st.session_state._requested_main_tab = TAB_ANALYSIS
                st.success("✓ Το PDF διαβάστηκε. Συνέχισε στην καρτέλα «2 · Ανάλυση & έλεγχος» →")
                st.rerun()
        if ok and auto_full and auto_api:
            _run_full_pipeline_ui(auto_provider, auto_api, auto_model, auto_language, instructions, style)
            st.rerun()
        if not ok:
            st.error(
                "Η ανάγνωση σταμάτησε με ασφάλεια — το PDF μπορεί να μην είναι το σωστό Astrodienst Data Sheet, ή η μορφή του διαφέρει."
            )
            with st.expander("Τεχνική λεπτομέρεια"):
                st.code(str(err))
    if st.session_state.chart and not pdf:
        st.info(
            f"Ήδη ελεγμένος χάρτης στη συνεδρία: **{st.session_state.chart.name}**. "
            "Ανέβασε νέο PDF μόνο αν θέλεις να τον αντικαταστήσεις, "
            "ή πάτα «🔄 Νέα ανάλυση» στο πλάι."
        )
        st.button(
            "Συνέχεια στην Ανάλυση & έλεγχο →",
            type="primary",
            width="stretch",
            on_click=_request_main_tab,
            args=(TAB_ANALYSIS,),
        )
    if st.session_state.chart:
        _privacy_panel(st.session_state.chart)
    _auto_result_panel()
    if st.session_state.chart is not None and _resumable():
        with st.container(border=True):
            st.markdown("#### 💾 Υπάρχει μισοτελειωμένη εργασία για αυτόν τον χάρτη")
            st.caption(
                "Η διαδικασία είχε σταματήσει. Η «Συνέχεια» ξεκινά από το καλύτερο κείμενο που είχε γραφτεί "
                "(και, αν η ανάλυση είχε περάσει, από το τελικό έντυπο), χωρίς να πληρώσεις ξανά τη δημιουργία από την αρχή."
            )
            _cp = _checkpoint()
            st.download_button(
                "⬇️ Λήψη προσχεδίου ανάλυσης (για ασφάλεια)",
                build_analysis_docx(st.session_state.chart.name, _cp["analysis"]),
                file_name="Prosxedio_Analysis.docx",
                width="stretch",
                key="draft_download",
            )
            if auto_full and auto_api:
                if st.button("▶️ Συνέχεια από εκεί που σταμάτησε", type="primary", width="stretch", key="resume_run"):
                    _run_full_pipeline_ui(auto_provider, auto_api, auto_model, auto_language, instructions, style)
                    st.rerun()
                if st.button("Ξεκίνα από την αρχή (νέα ανάλυση για τον ίδιο χάρτη)", width="stretch", key="fresh_run"):
                    _run_full_pipeline_ui(auto_provider, auto_api, auto_model, auto_language, instructions, style, fresh=True)
                    st.rerun()
            else:
                st.caption("Για να συνεχίσεις, ενεργοποίησε την πλήρη αυτόματη διαδικασία και όρισε κλειδί API παραπάνω.")

instructions_text = (
    docx_text(instructions.getvalue()) if instructions else default_instructions_text
)
style_text = docx_text(style.getvalue()) if style else default_style_text
instructions_name = instructions.name if instructions else "Ενσωματωμένες οδηγίες v6"
style_name = style.name if style else "Ενσωματωμένος καθαρός οδηγός ύφους"

# Ό,τι ακολουθεί (εντολή, έγγραφα, μηνύματα) χρησιμοποιεί τον χάρτη με τις
# επιλογές απορρήτου εφαρμοσμένες.
chart = _shared_chart(st.session_state.chart)
with tab4:
    st.subheader("Δημιουργία και έλεγχος πλήρους ανάλυσης")
    # Προειδοποιήσεις του parser (π.χ. δεν αναγνωρίστηκαν δυναμικές όψεις)
    # εμφανίζονται πάντα -- πριν δεν φαίνονταν πουθενά.
    for _w in getattr(st.session_state.chart, "warnings", None) or []:
        st.warning("⚠️ " + _w)
    language = st.selectbox(
        "Γλώσσα τελικού εντύπου πελάτη",
        ["Ελληνικά", "Αγγλικά"],
        key="language",
        help="Ορίζει τη γλώσσα του τελικού εντύπου. Η τεχνική ανάλυση γίνεται δεκτή και στις δύο γλώσσες.",
    )
    personal = {"Όνομα": chart.name if chart else ""}
    prompt = ""
    if chart:
        prompt = build_master_prompt(
            chart, personal, language, instructions_text, style_text, instructions_name, style_name
        )

    if not chart:
        st.warning("Δεν υπάρχει ελεγμένος χάρτης. Ξεκίνα από την καρτέλα «1 · Αρχεία».")
    else:
        checklist = {
            "12 ακμές": len(chart.cusps) == 12,
            "Βόρειος Δεσμός": any(p.name == "Βόρειος Δεσμός" for p in chart.points),
            "Νότιος Δεσμός": any(p.name == "Νότιος Δεσμός" for p in chart.points),
            "Πίνακας όψεων": bool(chart.aspects),
            "Οδηγίες v6 μόνιμα ενσωματωμένες": bool(instructions_text),
            "Καθαρός οδηγός ύφους ενσωματωμένος": bool(style_text),
        }
        ready = all(checklist.values())
        with st.expander("Λίστα ελέγχου πριν τη δημιουργία", expanded=not ready):
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Έλεγχος": k, "Κατάσταση": "✓" if v else "Λείπει"}
                        for k, v in checklist.items()
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
        if not ready:
            st.markdown(
                '<div class="warn">⚠ Η αυτόματη δημιουργία παραμένει κλειδωμένη μέχρι να ολοκληρωθούν όλοι οι έλεγχοι παραπάνω.</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        col_auto, col_manual = st.columns(2)

        with col_auto:
            with st.container(border=True):
                st.markdown("#### 🤖 Αυτόματη δημιουργία")
                provider, api, model = _api_choice("analysis")
                rounds_cap = _max_rounds()
                st.caption(
                    "Η ανάλυση ελέγχεται αυτόματα και, αν δεν περάσει, διορθώνεται ξανά και ξανά "
                    f"μέχρι να περάσει τους ελέγχους ({_limits_text(rounds_cap)})."
                )
                if st.button(
                    "Δημιουργία πλήρους ανάλυσης",
                    type="primary",
                    disabled=not ready or not api,
                    width="stretch",
                ):
                    a_progress, a_finish = _progress_panel((P_ANALYSIS,))
                    _a_sig = analysis_signature(language, instructions_text, style_text, chart)
                    with st.status(
                        "Λεπτομέρειες γύρων", expanded=False
                    ) as status:

                        def _on_round(r):
                            a_progress(P_ANALYSIS, r)
                            icon = "✓" if r.ok else "✗"
                            status.write(
                                f"{icon} Γύρος {r.number} ({r.kind}): "
                                + (
                                    "πέρασε τον έλεγχο."
                                    if r.ok
                                    else f"{r.error_count} σφάλματα — "
                                    + (
                                        "στέλνονται για διόρθωση…"
                                        if rounds_cap == 0 or r.number < rounds_cap
                                        else "έφτασε το όριο ασφαλείας γύρων."
                                    )
                                )
                            )

                        try:
                            outcome = generate_validated(
                                api,
                                prompt,
                                validate=_with_review(
                                    lambda t: validate_analysis(chart, t, personal), provider, api, model, KIND_ANALYSIS
                                ),
                                model=model,
                                max_rounds=rounds_cap,
                                usage=_case_usage(model),
                                on_round=_on_round,
                                complete=completer(provider, _effort()),
                                stall_rounds=_stall_rounds(),
                                max_cost_usd=_max_cost(),
                                start_text=_analysis_resume_text(_a_sig),
                            )
                            a_finish()
                            st.session_state.analysis_sig = _a_sig
                            st.session_state.analysis = outcome.text
                            st.session_state.analysis_docx_bytes = None
                            st.session_state.analysis_docx_name = ""
                            st.session_state.validation = outcome.validation
                            st.session_state.analysis_source = "api"
                            status.update(
                                label=(
                                    "✓ Η ανάλυση πέρασε τους ελέγχους δεδομένων, δομής και ασφαλούς γλώσσας."
                                    if outcome.ok
                                    else "Η ανάλυση " + _stop_text(outcome.stop_reason, rounds_cap)
                                ),
                                state="complete" if outcome.ok else "error",
                                expanded=not outcome.ok,
                            )
                            if outcome.usage:
                                st.caption("💶 Κατανάλωση πελάτη ως τώρα: " + outcome.usage.describe(_eur_rate()))
                        except Exception as e:
                            a_finish()
                            partial = getattr(e, "partial", None)
                            if partial is not None:  # v19.5: η πρόοδος δεν χάνεται
                                st.session_state.analysis_sig = _a_sig
                                st.session_state.analysis = partial.text
                                st.session_state.validation = partial.validation
                                st.session_state.analysis_source = "api"
                                st.info("💾 Η πρόοδος κρατήθηκε· πάτα ξανά «Δημιουργία πλήρους ανάλυσης» για συνέχεια από εκεί.")
                            status.update(label="Η δημιουργία απέτυχε.", state="error")
                            _show_api_error(e, provider)
                _analysis_result_panel("api", chart.name)
                if not ready:
                    st.caption("Κλειδωμένο μέχρι να ολοκληρωθεί η λίστα ελέγχου παραπάνω.")

        with col_manual:
            with st.container(border=True):
                st.markdown("#### 📋 Χειροκίνητη διαδρομή")
                st.markdown("**1. Κατέβασε το δελτίο και στείλε το στο ChatGPT/Claude**")
                audit = build_audit_docx(chart, personal, prompt)
                st.download_button(
                    "⬇️ Λήψη δελτίου ελέγχου και πλήρους εντολής (Word)",
                    audit,
                    file_name="AstroCheck_Elegxos_kai_Odigies.docx",
                    width="stretch",
                )
                with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude"):
                    if language == "Αγγλικά":
                        st.info("Επιλεγμένη γλώσσα: Αγγλικά. Η πρώτη γραμμή του μηνύματος ζητά αγγλική ανάλυση.")
                    st.code(analysis_paste_message(language), language=None)
                st.markdown("**2. Ανέβασε την ανάλυση σε Word και έλεγξέ την**")
                uploaded_analysis = st.file_uploader(
                    "Τελική ανάλυση από ChatGPT/Claude (.docx)",
                    type=["docx"],
                    key=f"analysis_docx_{st.session_state.uploader_gen}",
                )
                if st.button("Έλεγχος ανάλυσης", width="stretch", disabled=not uploaded_analysis):
                    try:
                        uploaded_bytes = uploaded_analysis.getvalue()
                        extracted = docx_text(uploaded_bytes)
                        st.session_state.analysis = extracted
                        st.session_state.analysis_docx_bytes = uploaded_bytes
                        st.session_state.analysis_docx_name = uploaded_analysis.name
                        st.session_state.analysis_docx_hash = fingerprint(uploaded_bytes)
                        st.session_state.validation = validate_analysis(chart, extracted, personal)
                        st.session_state.analysis_source = "docx"
                    except Exception as e:
                        st.error("Δεν ήταν δυνατή η ανάγνωση του Word.")
                        with st.expander("Τεχνική λεπτομέρεια"):
                            st.code(str(e))
                if "analysis" in _stale and uploaded_analysis is not None:
                    st.info("Ανέβηκε νέο Word. Πάτα «Έλεγχος ανάλυσης» για να ελεγχθεί.")
                _analysis_result_panel("docx", chart.name)
                st.divider()
                st.caption("Εναλλακτικά, μπορείς να επικολλήσεις το πλήρες κείμενο.")
                pasted = st.text_area(
                    "Επικολλημένη ανάλυση",
                    height=150,
                    key="pasted_analysis",
                    label_visibility="collapsed",
                    placeholder="Επικόλλησε εδώ το πλήρες κείμενο της ανάλυσης…",
                )
                if st.button(
                    "Έλεγχος πληρότητας επικολλημένου κειμένου",
                    width="stretch",
                    disabled=not pasted,
                ):
                    st.session_state.analysis = pasted
                    st.session_state.analysis_docx_bytes = None
                    st.session_state.analysis_docx_name = ""
                    st.session_state.validation = validate_analysis(chart, pasted, personal)
                    st.session_state.analysis_source = "paste"
                _analysis_result_panel("paste", chart.name)

with tab6:
    st.subheader("Τελική αναδιατύπωση")
    st.caption(
        "Η αναδιατύπωση αλλάζει μόνο το ύφος. Οι Οίκοι, τα δεδομένα και οι ενότητες μένουν ίδια."
    )
    rewrite_command_path = (
        Path(__file__).resolve().parent / "Desmeftiki_Entoli_Telikis_Anadiatyposis_v9.docx"
    )
    if rewrite_command_path.exists():
        st.download_button(
            "⬇️ Λήψη Δεσμευτικής Εντολής Τελικής Αναδιατύπωσης",
            rewrite_command_path.read_bytes(),
            file_name="Desmeftiki_Entoli_Telikis_Anadiatyposis_v9.docx",
            width="stretch",
        )
    else:
        st.warning("Λείπει η ενσωματωμένη Δεσμευτική Εντολή Τελικής Αναδιατύπωσης.")
    with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude", expanded=True):
        _client_name = chart.name if chart and chart.name else "[ΟΝΟΜΑ]"
        # v14: το μήνυμα χτίζεται από τη γλώσσα που έχει πράγματι η ελεγμένη ανάλυση.
        _rewrite_message = rewrite_paste_message(
            _client_name, st.session_state.get("language"), st.session_state.analysis or ""
        )
        st.code(_rewrite_message, language=None)
    for _note in language_notes(st.session_state.get("language"), st.session_state.analysis or ""):
        st.info(_note)
    if not (
        chart
        and st.session_state.analysis
        and st.session_state.validation
        and st.session_state.validation.ok
    ):
        st.warning(
            "Πρώτα χρειάζεται ελεγμένη τεχνική ανάλυση από την καρτέλα «2 · Ανάλυση & έλεγχος»."
        )
    else:
        with st.container(border=True):
            st.markdown("#### 🤖 Αυτόματη αναδιατύπωση")
            rw_provider, rw_api, rw_model = _api_choice("rewrite")
            rw_rounds_cap = _max_rounds()
            st.caption(
                "Στέλνεται η Δεσμευτική Εντολή μαζί με την ελεγμένη ανάλυση. Το τελικό έντυπο ελέγχεται "
                f"αυτόματα και, αν δεν περάσει, διορθώνεται ξανά μέχρι να περάσει τους ελέγχους ({_limits_text(rw_rounds_cap)}). "
                "Ο έλεγχος δεν κρίνει αν διατηρήθηκε όλο το νόημα· διάβασε το έντυπο πριν το παραδώσεις."
            )
            if st.button(
                "Δημιουργία τελικού εντύπου",
                type="primary",
                disabled=not rw_api or not rewrite_command_path.exists(),
                width="stretch",
            ):
                r_progress, r_finish = _progress_panel((P_REWRITE,))
                _r_sig = rewrite_signature(
                    st.session_state.get("analysis_sig", ""),
                    st.session_state.get("language"),
                    docx_text(rewrite_command_path.read_bytes()),
                )
                with st.status("Λεπτομέρειες γύρων", expanded=False) as rw_status:

                    def _on_rewrite_round(r):
                        r_progress(P_REWRITE, r)
                        rw_status.write(
                            f"{'✓' if r.ok else '✗'} Γύρος {r.number} ({r.kind}): "
                            + (r.summary if r.kind == "γύρος ποιότητας" else "πέρασε τον έλεγχο." if r.ok else f"{r.error_count} σφάλματα.")
                        )

                    try:
                        _name = chart.name if chart and chart.name else "[ΟΝΟΜΑ]"
                        _analysis_text = st.session_state.analysis
                        rw_prompt = build_rewrite_prompt(
                            docx_text(rewrite_command_path.read_bytes()),
                            _analysis_text,
                            _name,
                            rewrite_language_block(_name, st.session_state.get("language"), _analysis_text),
                        )
                        rw_outcome = generate_validated(
                            rw_api,
                            rw_prompt,
                            validate=_with_review(
                                lambda t: validate_rewrite(chart, _analysis_text, t, personal),
                                rw_provider, rw_api, rw_model, KIND_REWRITE, _analysis_text,
                            ),
                            model=rw_model,
                            usage=_case_usage(rw_model),
                            max_rounds=rw_rounds_cap,
                            on_round=_on_rewrite_round,
                            complete=completer(rw_provider, _effort()),
                            revision_template=REWRITE_REVISION_TEMPLATE,
                            polish=True,
                            stall_rounds=_stall_rounds(),
                            max_cost_usd=_max_cost(),
                            start_text=_rewrite_resume_text(_analysis_text, _r_sig),
                        )
                        r_finish()
                        st.session_state.rewrite_validation = rw_outcome.validation
                        st.session_state.rewrite_sig = _r_sig
                        st.session_state.rewrite_text = rw_outcome.text
                        st.session_state.rewrite_docx_bytes = build_analysis_docx(_name, rw_outcome.text)
                        st.session_state.rewrite_docx_name = "Teliki_Analysi.docx"
                        st.session_state.rewrite_docx_hash = None
                        st.session_state.rewrite_analysis_hash = fingerprint(_analysis_text)
                        st.session_state.rewrite_source = "api"
                        rw_status.update(
                            label=(
                                "✓ Το τελικό έντυπο πέρασε τους ελέγχους δεδομένων, δομής και ασφαλούς γλώσσας."
                                if rw_outcome.ok
                                else "Το τελικό έντυπο " + _stop_text(rw_outcome.stop_reason, rw_rounds_cap)
                            ),
                            state="complete" if rw_outcome.ok else "error",
                            expanded=not rw_outcome.ok,
                        )
                        if rw_outcome.usage:
                            st.caption("💶 Κατανάλωση πελάτη ως τώρα: " + rw_outcome.usage.describe(_eur_rate()))
                    except Exception as e:
                        r_finish()
                        partial = getattr(e, "partial", None)
                        if partial is not None:  # v19.5: η πρόοδος δεν χάνεται
                            st.session_state.rewrite_validation = partial.validation
                            st.session_state.rewrite_sig = _r_sig
                            st.session_state.rewrite_text = partial.text
                            st.session_state.rewrite_docx_bytes = build_analysis_docx(_name, partial.text)
                            st.session_state.rewrite_docx_name = "Teliki_Analysi.docx"
                            st.session_state.rewrite_analysis_hash = fingerprint(_analysis_text)
                            st.session_state.rewrite_source = "api"
                            st.info("💾 Η πρόοδος κρατήθηκε· πάτα ξανά «Δημιουργία τελικού εντύπου» για συνέχεια από εκεί.")
                        rw_status.update(label="Η αναδιατύπωση απέτυχε.", state="error")
                        _show_api_error(e, rw_provider)
        st.markdown("**Ή ανέβασε έντυπο που έφτιαξες χειροκίνητα:**")
        rewritten = st.file_uploader(
            "Τελική αναδιατύπωση (.docx)",
            type=["docx"],
            key=f"rewrite_docx_{st.session_state.uploader_gen}",
        )
        if st.button("Έλεγχος τελικού εντύπου", disabled=not rewritten, width="stretch"):
            rewritten_bytes = rewritten.getvalue()
            rewritten_text = docx_text(rewritten_bytes)
            result = validate_rewrite(chart, st.session_state.analysis, rewritten_text, personal)
            st.session_state.rewrite_validation = result
            st.session_state.rewrite_docx_bytes = rewritten_bytes
            st.session_state.rewrite_docx_name = rewritten.name
            st.session_state.rewrite_docx_hash = fingerprint(rewritten_bytes)
            st.session_state.rewrite_analysis_hash = fingerprint(st.session_state.analysis)
            st.session_state.rewrite_source = "docx"
        if "rewrite" in _stale and rewritten is not None:
            st.info("Ανέβηκε νέο Word ή άλλαξε η ανάλυση. Πάτα «Έλεγχος τελικού εντύπου» για νέο έλεγχο.")
        result = st.session_state.get("rewrite_validation")
        if result:
            if st.session_state.get("rewrite_docx_bytes"):
                for _note in language_notes(
                    st.session_state.get("language"),
                    "",
                    docx_text(st.session_state.rewrite_docx_bytes),
                ):
                    st.warning(_note)
            if result.ok:
                st.markdown(f'<div class="ok">{result.summary()}</div>', unsafe_allow_html=True)
                for note in getattr(result, "warnings", []):
                    st.warning(note)
                st.download_button(
                    "⬇️ Λήψη τελικού εντύπου",
                    st.session_state.rewrite_docx_bytes,
                    file_name=st.session_state.rewrite_docx_name,
                    type="primary",
                    width="stretch",
                )
            else:
                st.markdown(f'<div class="warn">⚠ {result.summary()}</div>', unsafe_allow_html=True)
                with st.expander("Λεπτομέρειες", expanded=True):
                    for line in result.details_lines():
                        st.write("•", line)
                    for note in getattr(result, "warnings", []):
                        st.write("• (προς ανάγνωση, δεν κλειδώνει)", note)
                st.button("Λήψη τελικής αναδιατύπωσης — κλειδωμένη", disabled=True, width="stretch")
