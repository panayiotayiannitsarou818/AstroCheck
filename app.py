import streamlit as st
import pandas as pd
from pathlib import Path
from prompts import build_master_prompt
from docx_builder import build_audit_docx, build_analysis_docx
from generator import generate_analysis
from reference_loader import (
    docx_text, load_default_references,
)
from validator import validate_analysis, validate_rewrite
from case_state import reset_case_state, handle_pdf_upload

FULL_ANALYSIS_PASTE_MESSAGE = """Σου επισυνάπτω ένα έγγραφο AstroCheck.

Θεώρησε αποκλειστικά την ενότητα «Πλήρης εντολή για δημιουργία ανάλυσης», από τη φράση «ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ» μέχρι το τέλος της, ως τη δεσμευτική σου εντολή.

Ακολούθησε πιστά όλες τις οδηγίες και χρησιμοποίησε αποκλειστικά τα ελεγμένα αστρολογικά δεδομένα, τα προσωπικά στοιχεία που περιλαμβάνονται στο AstroCheck και όποιο άλλο υλικό επιτρέπεται ρητά από τη δεσμευτική εντολή. Μην επινοήσεις πληροφορίες, μη χρησιμοποιήσεις μνήμη ή προηγούμενες συνομιλίες και μην αντιγράψεις προσωπικά ή αστρολογικά στοιχεία από τον οδηγό ύφους.

Δημιούργησε την πλήρη αστρολογική ανάλυση και παράδωσέ την σε ολοκληρωμένο, καλαίσθητο αρχείο Word. Πριν από την παράδοση, κάνε προσεκτικό αυτοέλεγχο συνέπειας των Οίκων, κυβερνητών, όψεων, orb, κατηγοριών βαρύτητας, προσωπικών στοιχείων και ενοτήτων. Μην δηλώσεις ότι «έτρεξες τον validator»· ο πραγματικός validator θα εκτελεστεί στη συνέχεια μέσα στο AstroCheck Pro."""

REWRITE_PASTE_MESSAGE = """Σου επισυνάπτω δύο αρχεία: τη «Δεσμευτική Εντολή Τελικής Αναδιατύπωσης» και το AstroCheck_Analysi του/της {name}.

Θεώρησε τη Δεσμευτική Εντολή ως τη μοναδική δεσμευτική οδηγία διαδικασίας και ακολούθησέ την πιστά και στο σύνολό της, χωρίς παρεκκλίσεις. Θεώρησε το AstroCheck_Analysi ως τη μοναδική πηγή αστρολογικού και ερμηνευτικού περιεχομένου. Μην επινοήσεις ή αλλάξεις κανένα αστρολογικό δεδομένο και μην παραλείψεις κανένα ουσιαστικό ερμηνευτικό νόημα. Επιτρέπεται μόνο η αναδιοργάνωση, αναδιατύπωση, σύνθεση και συγχώνευση του ήδη επαληθευμένου περιεχομένου, ακριβώς όπως ορίζει η Δεσμευτική Εντολή.

Το τελικό έντυπο προορίζεται για τον πελάτη (κανόνας 20): μην εμφανίσεις μοίρες, orb, κατηγορίες βαρύτητας, Παράρτημα ή πίνακα όψεων, ενδείξεις πηγής ή ενότητες τεχνικού ελέγχου. Όπου η πηγή χρησιμοποιεί τεχνικό δεδομένο, κράτησε μόνο το ερμηνευτικό του νόημα.

Παρήγαγε την πλήρη ανθρωποποιημένη ανάλυση σύμφωνα με όλους τους κανόνες της Δεσμευτικής Εντολής. Πριν παραδώσεις, πραγματοποίησε τον προβλεπόμενο τριπλό τελικό έλεγχο — ποιότητα → απώλεια → εφεύρεση — και βεβαιώσου ότι η τελευταία πρόταση του εγγράφου είναι αυτούσια η υποχρεωτική πρόταση του κανόνα 19. Παράδωσε το τελικό αποτέλεσμα σε πλήρες, καλαίσθητο αρχείο Word. Κάνε μόνο αυτοέλεγχο· ο πραγματικός μηχανικός validator θα εκτελεστεί στη συνέχεια στο AstroCheck Pro."""

st.set_page_config(page_title="AstroCheck Pro", page_icon="✦", layout="wide")
st.markdown("""<style>
.stApp{background:#f5f7f3}.block-container{max-width:1180px;padding-top:2rem}.hero{background:#19332f;color:white;border-radius:22px;padding:30px 34px;margin-bottom:18px}.hero h1{margin:0 0 8px;font-family:Georgia;font-size:42px}.hero p{color:#dce8e2}.ok{padding:14px 16px;background:#e5f2e7;border-left:5px solid #39704c;border-radius:8px}.warn{padding:14px 16px;background:#fff1dd;border-left:5px solid #b7791f;border-radius:8px}div[data-testid="stMetric"]{background:white;border:1px solid #dce4df;padding:12px;border-radius:12px}.step-done{color:#2f6b46;font-weight:600}.step-pending{color:#8a8f8c}.step-warn{color:#b7791f;font-weight:600}</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>AstroCheck Pro</h1><p>Ανέβασε το Astrodienst PDF, δημιούργησε την ανάλυση και κατέβασε το τελικό Word.</p></div>',unsafe_allow_html=True)

if 'chart' not in st.session_state: st.session_state.chart=None
if 'analysis' not in st.session_state: st.session_state.analysis=''
if 'validation' not in st.session_state: st.session_state.validation=None
if 'analysis_docx_bytes' not in st.session_state: st.session_state.analysis_docx_bytes=None
if 'analysis_docx_name' not in st.session_state: st.session_state.analysis_docx_name=''
if 'rewrite_validation' not in st.session_state: st.session_state.rewrite_validation=None
if 'uploader_gen' not in st.session_state: st.session_state.uploader_gen=0  # αλλάζει τα keys των uploaders ώστε το "Νέα ανάλυση" να τους αδειάζει πραγματικά

# Τα tabs του Streamlit δεν άλλαζαν αυτόματα μετά την ανάγνωση ενός PDF.
# Έτσι ο χρήστης έβλεπε ότι ο χάρτης είχε φορτωθεί, αλλά παρέμενε στην
# «1 · Αρχεία» χωρίς εμφανή τρόπο συνέχειας.  Το προσωρινό request γράφεται
# από τα κουμπιά και εφαρμόζεται ΠΡΙΝ δημιουργηθεί το widget των tabs.
if st.session_state.get("_requested_main_tab"):
    st.session_state.main_tab = st.session_state.pop("_requested_main_tab")


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
            st.code("Ο έλεγχος AstroCheck εντόπισε τα εξής. Διόρθωσε ΜΟΝΟ αυτά τα σημεία, "
                    "χωρίς να αλλάξεις όψεις, orb, βαρύτητες ή ενότητες, και παράδωσε ξανά "
                    "ολόκληρο το Word:\n" + "\n".join(f"- {l}" for l in lines), language=None)


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
        st.download_button("⬇️ Λήψη ελεγμένης πλήρους ανάλυσης (Word)", final_doc,
                           file_name=final_name, type="primary", use_container_width=True,
                           key=f"download_analysis_{source}")
        st.button("Συνέχεια στην Τελική αναδιατύπωση →", use_container_width=True,
                  on_click=_request_main_tab, args=("3 · Τελική αναδιατύπωση",),
                  key=f"to_rewrite_{source}")
    else:
        suffix = ("Το Word απορρίφθηκε και η λήψη παραμένει κλειδωμένη."
                  if source == "docx" else "Η λήψη παραμένει κλειδωμένη.")
        _error_with_details(validation, suffix)
    with st.expander("Προεπισκόπηση κειμένου ανάλυσης"):
        st.text_area("Κείμενο ανάλυσης", st.session_state.analysis, height=380,
                     label_visibility="collapsed", key=f"preview_{source}")


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
analysis_ok = bool(st.session_state.analysis) and st.session_state.validation is not None and st.session_state.validation.ok
analysis_warn = bool(st.session_state.analysis) and st.session_state.validation is not None and not st.session_state.validation.ok

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
    _step("3. Τελική αναδιατύπωση", bool(st.session_state.rewrite_validation and st.session_state.rewrite_validation.ok))

    st.divider()
    st.caption("Τα δεδομένα επεξεργάζονται στη συνεδρία και δεν αποθηκεύονται από την εφαρμογή.")
    if st.button("🔄 Νέα ανάλυση (καθαρισμός όλων)", use_container_width=True,
                 help="Καθαρίζει τον χάρτη και τις αναλύσεις, ώστε να ξεκινήσεις με άλλο άτομο."):
        st.session_state.chart = None
        st.session_state.uploader_gen += 1  # αναγκάζει τους file_uploader να ξαναγίνουν "άδειοι"
        reset_case_state()
        st.rerun()

MAIN_TABS = ["1 · Αρχεία", TAB_ANALYSIS, "3 · Τελική αναδιατύπωση"]
# Μια συνεδρία που είχε ανοιχτή καρτέλα με παλιό όνομα (π.χ. «3 · Τεχνικό Word»,
# που καταργήθηκε) επιστρέφει με ασφάλεια στην πρώτη καρτέλα.
if st.session_state.get("main_tab") not in (None, *MAIN_TABS):
    st.session_state.main_tab = "1 · Αρχεία"
tab1,tab4,tab6=st.tabs(MAIN_TABS, key="main_tab", default="1 · Αρχεία")

with tab1:
    st.subheader("Ανέβασε μόνο το νέο PDF")
    st.success("✓ Οι οδηγίες και ο οδηγός ύφους είναι ενσωματωμένα.")
    pdf=st.file_uploader("Νέο Astrodienst Data Sheet",type=['pdf'],key=f"pdf_{st.session_state.uploader_gen}")
    with st.expander("Προχωρημένα: προαιρετική προσωρινή αντικατάσταση"):
        instructions=st.file_uploader("Νεότερες οδηγίες",type=['docx'],key=f"instructions_{st.session_state.uploader_gen}")
        style=st.file_uploader("Νεότερο πρότυπο ύφους",type=['docx'],key=f"style_{st.session_state.uploader_gen}")
    if pdf and st.button("Ανάγνωση και έλεγχος PDF",type="primary",use_container_width=True):
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
                st.error("Η ανάγνωση σταμάτησε με ασφάλεια — το PDF μπορεί να μην είναι το σωστό Astrodienst Data Sheet, ή η μορφή του διαφέρει.")
                with st.expander("Τεχνική λεπτομέρεια"): st.code(str(err))
    if st.session_state.chart and not pdf:
        st.info(f"Ήδη ελεγμένος χάρτης στη συνεδρία: **{st.session_state.chart.name}**. Ανέβασε νέο PDF μόνο αν θέλεις να τον αντικαταστήσεις, ή πάτα «🔄 Νέα ανάλυση» στο πλάι.")
        st.button(
            "Συνέχεια στην Ανάλυση & έλεγχο →",
            type="primary",
            use_container_width=True,
            on_click=_request_main_tab,
            args=(TAB_ANALYSIS,),
        )

instructions_text = docx_text(instructions.getvalue()) if instructions else default_instructions_text
style_text = docx_text(style.getvalue()) if style else default_style_text
instructions_name = instructions.name if instructions else "Ενσωματωμένες οδηγίες v5.3"
style_name = style.name if style else "Ενσωματωμένος καθαρός οδηγός ύφους"

chart=st.session_state.chart
with tab4:
    st.subheader("Δημιουργία και έλεγχος πλήρους ανάλυσης")
    language=st.selectbox("Γλώσσα τελικής ανάλυσης", ["Ελληνικά", "Αγγλικά"], key="language")
    personal={"Όνομα":chart.name if chart else ""}
    prompt=''
    if chart:
        prompt=build_master_prompt(chart,personal,language,instructions_text,style_text,instructions_name,style_name)


    if not chart: st.warning("Δεν υπάρχει ελεγμένος χάρτης. Ξεκίνα από την καρτέλα «1 · Αρχεία».")
    else:
        checklist={"12 ακμές":len(chart.cusps)==12,"Βόρειος Δεσμός":any(p.name=='Βόρειος Δεσμός' for p in chart.points),"Νότιος Δεσμός":any(p.name=='Νότιος Δεσμός' for p in chart.points),"Πίνακας όψεων":bool(chart.aspects),"Οδηγίες v5.3 μόνιμα ενσωματωμένες":bool(instructions_text),"Καθαρός οδηγός ύφους ενσωματωμένος":bool(style_text)}
        ready=all(checklist.values())
        with st.expander("Λίστα ελέγχου πριν τη δημιουργία", expanded=not ready):
            st.dataframe(pd.DataFrame([{"Έλεγχος":k,"Κατάσταση":"✓" if v else "Λείπει"} for k,v in checklist.items()]),use_container_width=True,hide_index=True)
        if not ready:
            st.markdown('<div class="warn">⚠ Η αυτόματη δημιουργία παραμένει κλειδωμένη μέχρι να ολοκληρωθούν όλοι οι έλεγχοι παραπάνω.</div>',unsafe_allow_html=True)

        st.divider()
        col_auto, col_manual = st.columns(2)

        with col_auto:
            with st.container(border=True):
                st.markdown("#### 🤖 Αυτόματη δημιουργία")
                st.caption("Χρειάζεται δικό σου OpenAI API key. Δεν αποθηκεύεται πουθενά.")
                api=st.text_input("OpenAI API key",type="password",label_visibility='collapsed',placeholder="sk-...")
                if st.button("Δημιουργία πλήρους ανάλυσης",type="primary",disabled=not ready or not api,use_container_width=True):
                    with st.spinner("Δημιουργείται η ανάλυση των 12 Οίκων…"):
                        try:
                            text=generate_analysis(api,prompt)
                            st.session_state.analysis=text
                            st.session_state.analysis_docx_bytes=None
                            st.session_state.analysis_docx_name=''
                            st.session_state.validation=validate_analysis(chart,text,personal)
                            st.session_state.analysis_source='api'
                        except Exception as e:
                            st.error("Η δημιουργία απέτυχε.")
                            with st.expander("Τεχνική λεπτομέρεια"): st.code(str(e))
                _analysis_result_panel("api", chart.name)
                if not ready:
                    st.caption("Κλειδωμένο μέχρι να ολοκληρωθεί η λίστα ελέγχου παραπάνω.")

        with col_manual:
            with st.container(border=True):
                st.markdown("#### 📋 Χειροκίνητη διαδρομή")
                st.markdown("**1. Κατέβασε το δελτίο και στείλε το στο ChatGPT/Claude**")
                audit=build_audit_docx(chart,personal,prompt)
                st.download_button("⬇️ Λήψη δελτίου ελέγχου και πλήρους εντολής (Word)",audit,file_name="AstroCheck_Elegxos_kai_Odigies.docx",use_container_width=True)
                with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude"):
                    st.code(FULL_ANALYSIS_PASTE_MESSAGE, language=None)
                st.markdown("**2. Ανέβασε την ανάλυση σε Word και έλεγξέ την**")
                uploaded_analysis=st.file_uploader(
                    "Τελική ανάλυση από ChatGPT/Claude (.docx)",
                    type=['docx'],
                    key=f"analysis_docx_{st.session_state.uploader_gen}",
                )
                if st.button("Έλεγχος ανάλυσης",use_container_width=True,disabled=not uploaded_analysis):
                    try:
                        uploaded_bytes=uploaded_analysis.getvalue()
                        extracted=docx_text(uploaded_bytes)
                        st.session_state.analysis=extracted
                        st.session_state.analysis_docx_bytes=uploaded_bytes
                        st.session_state.analysis_docx_name=uploaded_analysis.name
                        st.session_state.validation=validate_analysis(chart,extracted,personal)
                        st.session_state.analysis_source='docx'
                    except Exception as e:
                        st.error("Δεν ήταν δυνατή η ανάγνωση του Word.")
                        with st.expander("Τεχνική λεπτομέρεια"): st.code(str(e))
                _analysis_result_panel("docx", chart.name)
                st.divider()
                st.caption("Εναλλακτικά, μπορείς να επικολλήσεις το πλήρες κείμενο.")
                pasted=st.text_area("Επικολλημένη ανάλυση",height=150,key='pasted_analysis',label_visibility='collapsed',placeholder="Επικόλλησε εδώ το πλήρες κείμενο της ανάλυσης…")
                if st.button("Έλεγχος πληρότητας επικολλημένου κειμένου",use_container_width=True,disabled=not pasted):
                    st.session_state.analysis=pasted
                    st.session_state.analysis_docx_bytes=None
                    st.session_state.analysis_docx_name=''
                    st.session_state.validation=validate_analysis(chart,pasted,personal)
                    st.session_state.analysis_source='paste'
                _analysis_result_panel("paste", chart.name)

with tab6:
    st.subheader("Τελική αναδιατύπωση")
    st.caption("Η αναδιατύπωση αλλάζει μόνο το ύφος. Οι Οίκοι, τα δεδομένα και οι ενότητες μένουν ίδια.")
    rewrite_command_path = Path(__file__).resolve().parent / "Desmeftiki_Entoli_Telikis_Anadiatyposis_v8.docx"
    if rewrite_command_path.exists():
        st.download_button(
            "⬇️ Λήψη Δεσμευτικής Εντολής Τελικής Αναδιατύπωσης",
            rewrite_command_path.read_bytes(),
            file_name="Desmeftiki_Entoli_Telikis_Anadiatyposis_v8.docx",
            use_container_width=True,
        )
    else:
        st.warning("Λείπει η ενσωματωμένη Δεσμευτική Εντολή Τελικής Αναδιατύπωσης.")
    with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude", expanded=True):
        _client_name = (st.session_state.chart.name if st.session_state.chart and st.session_state.chart.name else "[ΟΝΟΜΑ]")
        st.code(REWRITE_PASTE_MESSAGE.format(name=_client_name), language=None)
    if not (chart and st.session_state.analysis and st.session_state.validation and st.session_state.validation.ok):
        st.warning("Πρώτα χρειάζεται ελεγμένη τεχνική ανάλυση από την καρτέλα «2 · Ανάλυση & έλεγχος».")
    else:
        rewritten=st.file_uploader("Τελική αναδιατύπωση (.docx)",type=['docx'],key=f"rewrite_docx_{st.session_state.uploader_gen}")
        if st.button("Έλεγχος τελικού εντύπου",disabled=not rewritten,use_container_width=True):
            rewritten_bytes=rewritten.getvalue()
            rewritten_text=docx_text(rewritten_bytes)
            result=validate_rewrite(chart,st.session_state.analysis,rewritten_text,personal)
            st.session_state.rewrite_validation=result
            st.session_state.rewrite_docx_bytes=rewritten_bytes
            st.session_state.rewrite_docx_name=rewritten.name
        result=st.session_state.get('rewrite_validation')
        if result:
            if result.ok:
                st.markdown(f'<div class="ok">{result.summary()}</div>',unsafe_allow_html=True)
                st.download_button("⬇️ Λήψη τελικού εντύπου",st.session_state.rewrite_docx_bytes,file_name=st.session_state.rewrite_docx_name,type="primary",use_container_width=True)
            else:
                st.markdown(f'<div class="warn">⚠ {result.summary()}</div>',unsafe_allow_html=True)
                with st.expander("Λεπτομέρειες",expanded=True):
                    for line in result.details_lines(): st.write("•",line)
                st.button("Λήψη τελικής αναδιατύπωσης — κλειδωμένη",disabled=True,use_container_width=True)

