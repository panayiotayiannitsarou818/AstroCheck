import dataclasses
import re
import streamlit as st
import pandas as pd
from pathlib import Path
from prompts import build_master_prompt
from docx_builder import build_audit_docx, build_analysis_docx
from generator import (
    DEFAULT_MAX_ROUNDS,
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
        st.rerun()

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
    if pdf and st.button("Ανάγνωση και έλεγχος PDF", type="primary", width="stretch"):
        with st.spinner("Διαβάζεται το PDF…"):
            ok, new_chart, err = handle_pdf_upload(pdf.getvalue(), pdf.name)
            # Η λογική "διάβασε -> καθάρισε προηγούμενη περίπτωση -> bump
            # uploader_gen -> αποθήκευσε chart" ζει στο case_state.handle_pdf_upload
            # (βλ. εκεί το γιατί) και ήδη γράφει κατευθείαν στο πραγματικό
            # st.session_state (δεν περάσαμε state=... εδώ) -- εδώ μένει μόνο
            # η παρουσίαση.
            if ok:
                st.session_state._requested_main_tab = TAB_ANALYSIS
                st.success("✓ Το PDF διαβάστηκε. Συνέχισε στην καρτέλα «2 · Ανάλυση & έλεγχος» →")
                st.rerun()
            else:
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
                st.caption(
                    f"Η ανάλυση ελέγχεται αυτόματα και, αν χρειαστεί, διορθώνεται αυτόματα "
                    f"(έως {DEFAULT_MAX_ROUNDS} γύροι συνολικά)."
                )
                if st.button(
                    "Δημιουργία πλήρους ανάλυσης",
                    type="primary",
                    disabled=not ready or not api,
                    width="stretch",
                ):
                    with st.status(
                        "Δημιουργείται η ανάλυση των 12 Οίκων…", expanded=True
                    ) as status:

                        def _on_round(r):
                            icon = "✓" if r.ok else "✗"
                            status.write(
                                f"{icon} Γύρος {r.number} ({r.kind}): "
                                + (
                                    "πέρασε τον έλεγχο."
                                    if r.ok
                                    else f"{r.error_count} σφάλματα — "
                                    + (
                                        "στέλνονται για διόρθωση…"
                                        if r.number < DEFAULT_MAX_ROUNDS
                                        else "τέλος γύρων."
                                    )
                                )
                            )

                        try:
                            outcome = generate_validated(
                                api,
                                prompt,
                                validate=lambda t: validate_analysis(chart, t, personal),
                                model=model,
                                max_rounds=DEFAULT_MAX_ROUNDS,
                                on_round=_on_round,
                                complete=completer(provider),
                            )
                            st.session_state.analysis = outcome.text
                            st.session_state.analysis_docx_bytes = None
                            st.session_state.analysis_docx_name = ""
                            st.session_state.validation = outcome.validation
                            st.session_state.analysis_source = "api"
                            status.update(
                                label=(
                                    "✓ Η ανάλυση πέρασε τον έλεγχο."
                                    if outcome.ok
                                    else "Η ανάλυση δεν πέρασε μετά από όλους τους γύρους — δες τα σφάλματα παρακάτω."
                                ),
                                state="complete" if outcome.ok else "error",
                                expanded=not outcome.ok,
                            )
                        except Exception as e:
                            status.update(label="Η δημιουργία απέτυχε.", state="error")
                            st.error(
                                f"Η δημιουργία απέτυχε. Έλεγξε το κλειδί {provider} και δοκίμασε ξανά."
                            )
                            with st.expander("Τεχνική λεπτομέρεια"):
                                st.code(str(e))
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
            st.caption(
                "Στέλνεται η Δεσμευτική Εντολή μαζί με την ελεγμένη ανάλυση. Το τελικό έντυπο ελέγχεται "
                f"αυτόματα και, αν χρειαστεί, διορθώνεται (έως {DEFAULT_MAX_ROUNDS} γύροι συνολικά). "
                "Ο έλεγχος δεν κρίνει αν διατηρήθηκε όλο το νόημα· διάβασε το έντυπο πριν το παραδώσεις."
            )
            if st.button(
                "Δημιουργία τελικού εντύπου",
                type="primary",
                disabled=not rw_api or not rewrite_command_path.exists(),
                width="stretch",
            ):
                with st.status("Γράφεται το τελικό έντυπο…", expanded=True) as rw_status:

                    def _on_rewrite_round(r):
                        rw_status.write(
                            f"{'✓' if r.ok else '✗'} Γύρος {r.number} ({r.kind}): "
                            + ("πέρασε τον έλεγχο." if r.ok else f"{r.error_count} σφάλματα.")
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
                            validate=lambda t: validate_rewrite(chart, _analysis_text, t, personal),
                            model=rw_model,
                            max_rounds=DEFAULT_MAX_ROUNDS,
                            on_round=_on_rewrite_round,
                            complete=completer(rw_provider),
                            revision_template=REWRITE_REVISION_TEMPLATE,
                        )
                        st.session_state.rewrite_validation = rw_outcome.validation
                        st.session_state.rewrite_docx_bytes = build_analysis_docx(_name, rw_outcome.text)
                        st.session_state.rewrite_docx_name = "Teliki_Analysi.docx"
                        st.session_state.rewrite_docx_hash = None
                        st.session_state.rewrite_analysis_hash = fingerprint(_analysis_text)
                        st.session_state.rewrite_source = "api"
                        rw_status.update(
                            label=(
                                "✓ Το τελικό έντυπο πέρασε τον έλεγχο."
                                if rw_outcome.ok
                                else "Το τελικό έντυπο δεν πέρασε μετά από όλους τους γύρους — δες τα σφάλματα παρακάτω."
                            ),
                            state="complete" if rw_outcome.ok else "error",
                            expanded=not rw_outcome.ok,
                        )
                    except Exception as e:
                        rw_status.update(label="Η αναδιατύπωση απέτυχε.", state="error")
                        st.error(f"Η αναδιατύπωση απέτυχε. Έλεγξε το κλειδί {rw_provider} και δοκίμασε ξανά.")
                        st.caption(f"Τεχνική λεπτομέρεια: {type(e).__name__}: {str(e)[:300]}")
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
