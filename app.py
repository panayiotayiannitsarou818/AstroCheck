import streamlit as st
import pandas as pd
from pathlib import Path
from prompts import build_master_prompt, build_orientation_source, fmt
from docx_builder import build_audit_docx, build_analysis_docx, build_orientation_docx
from generator import generate_analysis
from reference_loader import (
    docx_text, load_default_references, load_orientation_command,
    load_short_adult_example, load_short_teen_example, simple_docx_format_issues,
)
from astrology import movement_text, OPPOSITE_ANGLE
from validator import validate_analysis, validate_rewrite, validate_orientation
from case_state import reset_case_state, handle_pdf_upload

FULL_ANALYSIS_PASTE_MESSAGE = """Σου επισυνάπτω ένα έγγραφο AstroCheck.

Θεώρησε αποκλειστικά την ενότητα «Πλήρης εντολή για δημιουργία ανάλυσης», από τη φράση «ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ» μέχρι το τέλος της, ως τη δεσμευτική σου εντολή.

Ακολούθησε πιστά όλες τις οδηγίες και χρησιμοποίησε αποκλειστικά τα ελεγμένα αστρολογικά δεδομένα, τα προσωπικά στοιχεία που περιλαμβάνονται στο AstroCheck και όποιο άλλο υλικό επιτρέπεται ρητά από τη δεσμευτική εντολή. Μην επινοήσεις πληροφορίες, μη χρησιμοποιήσεις μνήμη ή προηγούμενες συνομιλίες και μην αντιγράψεις προσωπικά ή αστρολογικά στοιχεία από τον οδηγό ύφους.

Δημιούργησε την πλήρη αστρολογική ανάλυση και παράδωσέ την σε ολοκληρωμένο, καλαίσθητο αρχείο Word. Πριν από την παράδοση, κάνε προσεκτικό αυτοέλεγχο συνέπειας των Οίκων, κυβερνητών, όψεων, orb, κατηγοριών βαρύτητας, προσωπικών στοιχείων και ενοτήτων. Μην δηλώσεις ότι «έτρεξες τον validator»· ο πραγματικός validator θα εκτελεστεί στη συνέχεια μέσα στο AstroCheck Pro."""

REWRITE_PASTE_MESSAGE = """Αναδιατύπωσε την ελεγμένη τεχνική ανάλυση ακολουθώντας πιστά τη Δεσμευτική Εντολή Τελικής Αναδιατύπωσης. Μην προσθέσεις ή αλλάξεις αστρολογικά δεδομένα, προσωπικές πληροφορίες ή ενότητες. Παράδωσε το αποτέλεσμα σε ολοκληρωμένο Word. Κάνε μόνο αυτοέλεγχο — ο πραγματικός validator θα εκτελεστεί στη συνέχεια στο AstroCheck Pro."""

st.set_page_config(page_title="AstroCheck Pro", page_icon="✦", layout="wide")
st.markdown("""<style>
.stApp{background:#f5f7f3}.block-container{max-width:1180px;padding-top:2rem}.hero{background:#19332f;color:white;border-radius:22px;padding:30px 34px;margin-bottom:18px}.hero h1{margin:0 0 8px;font-family:Georgia;font-size:42px}.hero p{color:#dce8e2}.ok{padding:14px 16px;background:#e5f2e7;border-left:5px solid #39704c;border-radius:8px}.warn{padding:14px 16px;background:#fff1dd;border-left:5px solid #b7791f;border-radius:8px}div[data-testid="stMetric"]{background:white;border:1px solid #dce4df;padding:12px;border-radius:12px}.step-done{color:#2f6b46;font-weight:600}.step-pending{color:#8a8f8c}.step-warn{color:#b7791f;font-weight:600}</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>AstroCheck Pro</h1><p>Από το Astrodienst PDF σε ελεγμένα δεδομένα, πλήρεις οδηγίες και Word — με υποχρεωτική καταγραφή τετραγώνων, αντιθέσεων και συνόδων με γωνίες.</p></div>',unsafe_allow_html=True)

if 'chart' not in st.session_state: st.session_state.chart=None
if 'analysis' not in st.session_state: st.session_state.analysis=''
if 'validation' not in st.session_state: st.session_state.validation=None
if 'analysis_docx_bytes' not in st.session_state: st.session_state.analysis_docx_bytes=None
if 'analysis_docx_name' not in st.session_state: st.session_state.analysis_docx_name=''
if 'rewrite_validation' not in st.session_state: st.session_state.rewrite_validation=None
if 'orientation_validation' not in st.session_state: st.session_state.orientation_validation=None
if 'uploader_gen' not in st.session_state: st.session_state.uploader_gen=0  # αλλάζει τα keys των uploaders ώστε το "Νέα ανάλυση" να τους αδειάζει πραγματικά

# Τα tabs του Streamlit δεν άλλαζαν αυτόματα μετά την ανάγνωση ενός PDF.
# Έτσι ο χρήστης έβλεπε ότι ο χάρτης είχε φορτωθεί, αλλά παρέμενε στην
# «1 · Αρχεία» χωρίς εμφανή τρόπο συνέχειας.  Το προσωρινό request γράφεται
# από τα κουμπιά και εφαρμόζεται ΠΡΙΝ δημιουργηθεί το widget των tabs.
if st.session_state.get("_requested_main_tab"):
    st.session_state.main_tab = st.session_state.pop("_requested_main_tab")


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
confirmed_ready = bool(st.session_state.get('confirmed', False))
personal_extra_ready = any(st.session_state.get(k) for k in ('profession', 'family', 'projects', 'habits', 'experiences'))
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
    _step("2. Μαθηματικός έλεγχος", confirmed_ready)
    _step("3. Προσωπικό πλαίσιο", personal_extra_ready, optional_note="προαιρετικό, αλλά κάνει την ανάλυση πιο βιωματική")
    _step("4. Δημιουργία & έλεγχος πληρότητας", analysis_ok, warn=analysis_warn)

    st.divider()
    st.caption("Τα δεδομένα επεξεργάζονται στη συνεδρία και δεν αποθηκεύονται από την εφαρμογή.")
    if st.button("🔄 Νέα ανάλυση (καθαρισμός όλων)", use_container_width=True,
                 help="Καθαρίζει χάρτη, προσωπικό πλαίσιο και ανάλυση, ώστε να ξεκινήσεις καθαρά με το επόμενο άτομο."):
        st.session_state.chart = None
        st.session_state.uploader_gen += 1  # αναγκάζει τους file_uploader να ξαναγίνουν "άδειοι"
        reset_case_state()
        st.rerun()

MAIN_TABS = ["1 · Αρχεία","2 · Έλεγχος","3 · Προσωπικό πλαίσιο","4 · Δημιουργία","5 · Τεχνικό Word","6 · Τελική αναδιατύπωση","7 · Επαγγελματικός προσανατολισμός"]
tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs(MAIN_TABS, key="main_tab", default="1 · Αρχεία")

with tab1:
    st.subheader("Ανέβασε μόνο το νέο PDF")
    st.success("✓ Οι οδηγίες v5.3, ο καθαρός οδηγός ύφους και η κοινή εντολή επαγγελματικού προσανατολισμού με δύο λειτουργίες είναι ενσωματωμένα.")
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
                st.session_state._requested_main_tab = "2 · Έλεγχος"
                st.success("✓ Το PDF διαβάστηκε. Συνέχισε στην καρτέλα «2 · Έλεγχος» →")
                st.rerun()
            else:
                st.error("Η ανάγνωση σταμάτησε με ασφάλεια — το PDF μπορεί να μην είναι το σωστό Astrodienst Data Sheet, ή η μορφή του διαφέρει.")
                with st.expander("Τεχνική λεπτομέρεια"): st.code(str(err))
    if st.session_state.chart and not pdf:
        st.info(f"Ήδη ελεγμένος χάρτης στη συνεδρία: **{st.session_state.chart.name}**. Ανέβασε νέο PDF μόνο αν θέλεις να τον αντικαταστήσεις, ή πάτα «🔄 Νέα ανάλυση» στο πλάι.")
        st.button(
            "Συνέχεια στον Έλεγχο →",
            type="primary",
            use_container_width=True,
            on_click=_request_main_tab,
            args=("2 · Έλεγχος",),
        )

instructions_text = docx_text(instructions.getvalue()) if instructions else default_instructions_text
style_text = docx_text(style.getvalue()) if style else default_style_text
instructions_name = instructions.name if instructions else "Ενσωματωμένες οδηγίες v5.3"
style_name = style.name if style else "Ενσωματωμένος καθαρός οδηγός ύφους"

chart=st.session_state.chart
with tab2:
    if not chart: st.warning("Πρώτα ανέβασε και έλεγξε το PDF στην καρτέλα 1.")
    else:
        hard=[a for a in chart.aspects if a.aspect in ('Τετράγωνο','Αντίθεση')]
        # Ο validator (κανόνας 6Β) απαιτεί υποχρεωτικά και τις συνόδους με τις
        # γωνίες (Ωροσκόπος/Μεσουράνημα) -- π.χ. η σύνοδος Χείρωνα-Ωροσκόπου.
        # Πριν εμφανίζονταν μόνο τετράγωνα/αντιθέσεις εδώ, οπότε ο χρήστης δεν
        # είχε τρόπο να τις επιβεβαιώσει οπτικά, ενώ ο validator τις απαιτούσε.
        angle_conjunctions=[a for a in chart.aspects if a.aspect=='Σύνοδος' and (a.first in OPPOSITE_ANGLE or a.second in OPPOSITE_ANGLE)]
        a,b,c,d,e=st.columns(5); a.metric("Πλανήτες/σημεία",len(chart.points)); b.metric("Ακμές",len(chart.cusps)); c.metric("Όψεις Astrodienst",len(chart.aspects)); d.metric("Τετράγωνα/αντιθέσεις",len(hard)); e.metric("Σύνοδοι με γωνίες",len(angle_conjunctions))
        if chart.warnings:
            for w in chart.warnings: st.markdown(f'<div class="warn">⚠ {w}</div>',unsafe_allow_html=True)
        else: st.markdown('<div class="ok">✓ Αναγνωρίστηκαν 12 ακμές και ο πίνακας δυναμικών όψεων.</div>',unsafe_allow_html=True)
        st.subheader("Βασικά στοιχεία")
        st.write({"Όνομα":chart.name,"Ημερομηνία":chart.date,"Ώρα":chart.time,"Τόπος":chart.place,"Σύστημα":chart.house_system})
        with st.expander("Πλανήτες και τεχνική τοποθέτηση σε Οίκους"):
            st.dataframe(pd.DataFrame([{"Σημείο":p.name,"Θέση":fmt(p),"Οίκος":p.house,"Κίνηση":movement_text(p)} for p in chart.points]),use_container_width=True,hide_index=True)
        st.subheader("Υποχρεωτικά τετράγωνα και αντιθέσεις")
        st.dataframe(pd.DataFrame([{"Ζεύγος":f"{x.first}–{x.second}","Όψη":x.aspect,"Orb":x.orb_text,"Βαρύτητα":x.weight,"Πηγή":x.source} for x in hard]),use_container_width=True,hide_index=True)
        st.subheader("Υποχρεωτικές σύνοδοι με γωνίες (Ωροσκόπος/Μεσουράνημα)")
        if angle_conjunctions:
            st.dataframe(pd.DataFrame([{"Ζεύγος":f"{x.first}–{x.second}","Όψη":x.aspect,"Orb":x.orb_text,"Βαρύτητα":x.weight,"Πηγή":x.source} for x in angle_conjunctions]),use_container_width=True,hide_index=True)
        else:
            st.caption("Καμία σύνοδος πλανήτη/σημείου με τον Ωροσκόπο ή το Μεσουράνημα σε αυτόν τον χάρτη.")
        confirm=st.checkbox("Επιβεβαίωσα οπτικά ότι οι γραμμές παραπάνω συμφωνούν με τον πίνακα Astrodienst",key='confirmed')
        if not confirm: st.caption("👉 Η καρτέλα «4 · Δημιουργία» θα παραμείνει κλειδωμένη μέχρι την επιβεβαίωση.")
        else:
            st.markdown('<div class="ok">✓ Επιβεβαιώθηκε. Μπορείς να συνεχίσεις.</div>',unsafe_allow_html=True)
            next_col, orientation_col = st.columns(2)
            with next_col:
                st.button(
                    "Συνέχεια στο Προσωπικό πλαίσιο →",
                    use_container_width=True,
                    on_click=_request_main_tab,
                    args=("3 · Προσωπικό πλαίσιο",),
                )
            with orientation_col:
                st.button(
                    "Μετάβαση στον Επαγγελματικό προσανατολισμό →",
                    type="primary",
                    use_container_width=True,
                    on_click=_request_main_tab,
                    args=("7 · Επαγγελματικός προσανατολισμός",),
                )

with tab3:
    st.subheader("Πληροφορίες που επιτρέπεται να χρησιμοποιηθούν")
    st.caption("Προαιρετικό βήμα — μπορείς να προχωρήσεις με μόνο το όνομα. Ό,τι προσθέσεις εδώ κάνει την ανάλυση πιο βιωματική.")
    name_override=st.text_input("Όνομα για το τελικό έγγραφο",value=chart.name if chart else "",key='name_override')
    profession=st.text_input("Επάγγελμα και σπουδές",key='profession')
    family=st.text_input("Σχέσεις και οικογενειακή κατάσταση",key='family')
    projects=st.text_area("Σημαντικά έργα, ενδιαφέροντα ή στόχοι",key='projects')
    habits=st.text_area("Εργασιακές συνήθειες και καθημερινότητα",key='habits')
    experiences=st.text_area("Εμπειρίες που θέλεις να ενσωματωθούν",key='experiences')
    language=st.selectbox("Γλώσσα τελικής ανάλυσης",["Ελληνικά","Αγγλικά"],key='language')
    st.caption("Ό,τι δεν γράψεις εδώ δεν πρέπει να παρουσιαστεί ως γνωστό προσωπικό γεγονός.")

personal={"Όνομα":name_override,"Επάγγελμα και σπουδές":profession,"Οικογενειακή κατάσταση":family,"Έργα/ενδιαφέροντα":projects,"Εργασιακές συνήθειες":habits,"Εμπειρίες":experiences}
prompt=''
if chart:
    prompt=build_master_prompt(chart,personal,language,instructions_text,style_text,instructions_name,style_name)

with tab4:
    st.subheader("Δημιουργία πλήρους ανάλυσης")
    if not chart: st.warning("Δεν υπάρχει ελεγμένος χάρτης. Ξεκίνα από την καρτέλα «1 · Αρχεία».")
    else:
        checklist={"12 ακμές":len(chart.cusps)==12,"Βόρειος Δεσμός":any(p.name=='Βόρειος Δεσμός' for p in chart.points),"Νότιος Δεσμός":any(p.name=='Νότιος Δεσμός' for p in chart.points),"Πίνακας όψεων":bool(chart.aspects),"Χειροκίνητη επιβεβαίωση (καρτέλα 2)":st.session_state.get('confirmed',False),"Οδηγίες v5.3 μόνιμα ενσωματωμένες":bool(instructions_text),"Καθαρός οδηγός ύφους ενσωματωμένος":bool(style_text)}
        ready=all(checklist.values())
        with st.expander("Λίστα ελέγχου πριν τη δημιουργία", expanded=not ready):
            st.dataframe(pd.DataFrame([{"Έλεγχος":k,"Κατάσταση":"✓" if v else "Λείπει"} for k,v in checklist.items()]),use_container_width=True,hide_index=True)
        with st.expander("Προεπισκόπηση πλήρους εντολής"): st.text_area("",prompt,height=320,label_visibility='collapsed')
        st.download_button("⬇️ Λήψη πλήρους εντολής (.txt)",prompt,file_name="AstroCheck_Master_Prompt.txt",use_container_width=True)
        with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude"):
            st.code(FULL_ANALYSIS_PASTE_MESSAGE, language=None)

        if not ready:
            st.markdown('<div class="warn">⚠ Η αυτόματη δημιουργία παραμένει κλειδωμένη μέχρι να ολοκληρωθούν όλοι οι έλεγχοι παραπάνω (κυρίως η επιβεβαίωση στην καρτέλα 2).</div>',unsafe_allow_html=True)

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
                            if st.session_state.validation.ok:
                                st.success("✓ Πέρασε τον έλεγχο πληρότητας. Πήγαινε στην καρτέλα 5 →")
                            else:
                                st.error(st.session_state.validation.summary()+" Δες λεπτομέρειες στην καρτέλα 5. Η λήψη του Word παραμένει κλειδωμένη.")
                        except Exception as e:
                            st.error("Η δημιουργία απέτυχε.")
                            with st.expander("Τεχνική λεπτομέρεια"): st.code(str(e))
                if not ready:
                    st.caption("Κλειδωμένο μέχρι να ολοκληρωθεί η λίστα ελέγχου παραπάνω.")

        with col_manual:
            with st.container(border=True):
                st.markdown("#### 📋 Χειροκίνητη διαδρομή")
                st.caption("Το ChatGPT/Claude κάνει μόνο αυτοέλεγχο. Ανέβασε εδώ το Word ώστε ο πραγματικός μηχανικός validator του AstroCheck Pro να αποφασίσει αν μπορεί να παραδοθεί.")
                uploaded_analysis=st.file_uploader(
                    "Τελική ανάλυση από ChatGPT/Claude (.docx)",
                    type=['docx'],
                    key=f"analysis_docx_{st.session_state.uploader_gen}",
                )
                if st.button("Υποχρεωτικός έλεγχος τελικού Word",use_container_width=True,disabled=not uploaded_analysis):
                    try:
                        uploaded_bytes=uploaded_analysis.getvalue()
                        extracted=docx_text(uploaded_bytes)
                        st.session_state.analysis=extracted
                        st.session_state.analysis_docx_bytes=uploaded_bytes
                        st.session_state.analysis_docx_name=uploaded_analysis.name
                        st.session_state.validation=validate_analysis(chart,extracted,personal)
                        if st.session_state.validation.ok:
                            st.success("✓ Το τελικό Word πέρασε τον αυστηρό έλεγχο. Πήγαινε στην καρτέλα 5 →")
                        else:
                            st.error(st.session_state.validation.summary()+" Το Word απορρίφθηκε και η λήψη παραμένει κλειδωμένη.")
                    except Exception as e:
                        st.error("Δεν ήταν δυνατή η ανάγνωση του Word.")
                        with st.expander("Τεχνική λεπτομέρεια"): st.code(str(e))
                st.divider()
                st.caption("Εναλλακτικά, μπορείς να επικολλήσεις το πλήρες κείμενο.")
                pasted=st.text_area("Επικολλημένη ανάλυση",height=150,key='pasted_analysis',label_visibility='collapsed',placeholder="Επικόλλησε εδώ το πλήρες κείμενο της ανάλυσης…")
                if st.button("Έλεγχος πληρότητας επικολλημένου κειμένου",use_container_width=True,disabled=not pasted):
                    st.session_state.analysis=pasted
                    st.session_state.analysis_docx_bytes=None
                    st.session_state.analysis_docx_name=''
                    st.session_state.validation=validate_analysis(chart,pasted,personal)
                    if st.session_state.validation.ok:
                        st.success("✓ Πέρασε τον έλεγχο πληρότητας. Πήγαινε στην καρτέλα 5 →")
                    else:
                        st.error(st.session_state.validation.summary()+" Δες λεπτομέρειες στην καρτέλα 5.")

with tab5:
    st.subheader("Λήψη αρχείων")
    if chart:
        audit=build_audit_docx(chart,personal,prompt)
        st.download_button("⬇️ Λήψη δελτίου ελέγχου και πλήρους εντολής (Word)",audit,file_name="AstroCheck_Elegxos_kai_Odigies.docx",use_container_width=True)
        with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude"):
            st.code(FULL_ANALYSIS_PASTE_MESSAGE, language=None)
    if st.session_state.analysis:
        with st.expander("Προεπισκόπηση ανάλυσης"):
            st.text_area("",st.session_state.analysis,height=420,label_visibility='collapsed')
        validation=st.session_state.validation
        if validation is None:
            validation=validate_analysis(chart,st.session_state.analysis,personal)
            st.session_state.validation=validation
        st.subheader("Μηχανικός έλεγχος πληρότητας")
        if validation.ok:
            st.markdown(f'<div class="ok">{validation.summary()}</div>',unsafe_allow_html=True)
            original_docx=st.session_state.get('analysis_docx_bytes')
            if original_docx:
                final_doc=original_docx
                final_name=st.session_state.get('analysis_docx_name') or "Pliris_Astrologiki_Analysi.docx"
            else:
                final_doc=build_analysis_docx(name_override or chart.name,st.session_state.analysis)
                final_name="Pliris_Astrologiki_Analysi.docx"
            st.download_button("⬇️ Λήψη ελεγμένης πλήρους ανάλυσης (Word)",final_doc,file_name=final_name,type="primary",use_container_width=True)
        else:
            st.markdown(f'<div class="warn">⚠ {validation.summary()}</div>',unsafe_allow_html=True)
            with st.expander("Λεπτομέρειες ελέγχου πληρότητας",expanded=True):
                for line in validation.details_lines(): st.write("•",line)
            st.caption("Διόρθωσε το κείμενο στην πηγή του (ChatGPT/Claude/API) και ξαναπέρασέ το από την καρτέλα 4.")
            st.button("Λήψη πλήρους ανάλυσης (Word) — κλειδωμένο μέχρι να διορθωθεί η ανάλυση",disabled=True,use_container_width=True)
    else:
        st.info("Μετά την αυτόματη δημιουργία ή τον χειροκίνητο έλεγχο επικολλημένου κειμένου στην καρτέλα 4, θα εμφανιστεί εδώ το τελικό Word.")

with tab6:
    st.subheader("Δεύτερος έλεγχος της ανθρώπινης αναδιατύπωσης")
    st.caption("Η αναδιατύπωση επιτρέπεται να αλλάξει μόνο το ύφος. Δεν επιτρέπεται να αλλάξει Οίκους, προσωπικά δεδομένα ή να προσθέσει νέες ενότητες.")
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
        st.code(REWRITE_PASTE_MESSAGE, language=None)
    if not (chart and st.session_state.analysis and st.session_state.validation and st.session_state.validation.ok):
        st.warning("Πρώτα χρειάζεται ελεγμένη τεχνική ανάλυση από τις καρτέλες 4–5.")
    else:
        rewritten=st.file_uploader("Τελική αναδιατύπωση (.docx)",type=['docx'],key=f"rewrite_docx_{st.session_state.uploader_gen}")
        if st.button("Έλεγχος τελικής αναδιατύπωσης",disabled=not rewritten,use_container_width=True):
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
                st.download_button("⬇️ Λήψη τελικής ελεγμένης αναδιατύπωσης",st.session_state.rewrite_docx_bytes,file_name=st.session_state.rewrite_docx_name,type="primary",use_container_width=True)
            else:
                st.markdown(f'<div class="warn">⚠ {result.summary()}</div>',unsafe_allow_html=True)
                with st.expander("Λεπτομέρειες",expanded=True):
                    for line in result.details_lines(): st.write("•",line)
                st.button("Λήψη τελικής αναδιατύπωσης — κλειδωμένη",disabled=True,use_container_width=True)

with tab7:
    st.subheader("Προαιρετική υπηρεσία επαγγελματικού προσανατολισμού")
    st.info("Η υπηρεσία αυτή είναι χωριστή από τη βασική ανάλυση των 12 Οίκων και ενεργοποιείται μόνο όταν την έχει επιλέξει ο πελάτης.")
    service=st.selectbox(
        "Επιλεγμένη υπηρεσία",
        ["Καμία", "Παιδί/έφηβος", "Ενήλικας σε αλλαγή επαγγελματικής πορείας"],
        key='orientation_service',
    )
    if service == "Καμία":
        st.caption("Δεν θα δημιουργηθεί επαγγελματικός προσανατολισμός.")
    else:
        presentation=st.selectbox(
            "Τρόπος παρουσίασης στον πελάτη",
            ["Απλή και πρακτική", "Αναλυτική με αστρολογική τεκμηρίωση"],
            key='orientation_presentation',
            help=("Η απλή παρουσίαση δεν εμφανίζει τεχνική ορολογία στο Word του πελάτη. "
                  "Η αναλυτική εμφανίζει πλανήτες, Οίκους, όψεις, orb και βαρύτητα."),
        )
        if service == "Ενήλικας σε αλλαγή επαγγελματικής πορείας" and presentation == "Απλή και πρακτική":
            st.success(
                "Θα ζητηθεί σύντομο κείμενο 2–3 σελίδων, με καθημερινή γλώσσα, "
                "4–6 ταλέντα, 4–5 επαγγελματικούς τομείς και σύντομη τελική σύνθεση."
            )
        elif service == "Παιδί/έφηβος" and presentation == "Απλή και πρακτική":
            st.success(
                "Θα ζητηθεί σύντομο, φιλικό κείμενο 2–3 σελίδων για έφηβο, με απλή "
                "γλώσσα και χωρίς τις εκτενείς ενότητες της αναλυτικής έκδοσης."
            )
        if not (chart and st.session_state.analysis and st.session_state.validation and st.session_state.validation.ok):
            st.warning("Πρώτα ολοκλήρωσε και έλεγξε την τεχνική ανάλυση στις καρτέλες 4–5.")
            st.stop()

        cyprus_school = None
        if service == "Παιδί/έφηβος":
            cyprus_school = st.radio(
                "Φοιτά στο κυπριακό εκπαιδευτικό σύστημα;",
                ["Ναι", "Όχι"],
                index=None,
                key="orientation_cyprus_school",
                horizontal=True,
                help=("Η απάντηση είναι υποχρεωτική. Με «Ναι» ενεργοποιείται ξεχωριστή "
                      "ενότητα για τις ΟΜΠ και τις εκπαιδευτικές διαδρομές της Κύπρου."),
            )
            if cyprus_school is None:
                st.info("Επίλεξε «Ναι» ή «Όχι» για να δημιουργηθεί σωστά η εντολή του παιδιού/εφήβου.")
                st.stop()
            service_title="Ανάδειξη Ταλέντων και Επαγγελματικός Προσανατολισμός Παιδιού/Εφήβου"
            output_name="AstroCheck_Prosanatolismos_Paidiou_Efivou.docx"
        else:
            service_title="Ανάδειξη Ταλέντων και Επαγγελματικός Αναπροσανατολισμός Ενήλικα"
            output_name="AstroCheck_Anaprosanatolismos_Enilikou.docx"

        context={
            "Όνομα": name_override or chart.name,
            "Τύπος υπηρεσίας": service,
            "Τρόπος παρουσίασης": presentation,
        }
        if service == "Παιδί/έφηβος":
            context["Φοίτηση στο κυπριακό εκπαιδευτικό σύστημα"] = cyprus_school

        st.caption("Δεν ζητούνται πρόσθετα προσωπικά, ψυχολογικά, σχολικά ή οικονομικά δεδομένα. Η υπηρεσία παρουσιάζει μόνο συμβολικές πιθανότητες προς διερεύνηση από τον ελεγμένο χάρτη.")

        command_text=load_orientation_command(service)
        orientation_source=build_orientation_source(chart)
        style_example_text = ""
        if service == "Ενήλικας σε αλλαγή επαγγελματικής πορείας" and presentation == "Απλή και πρακτική":
            style_example_text = load_short_adult_example()
        elif service == "Παιδί/έφηβος" and presentation == "Απλή και πρακτική":
            style_example_text = load_short_teen_example()
        orientation_doc=build_orientation_docx(
            name_override or chart.name, service_title, context, command_text,
            orientation_source, style_example_text=style_example_text,
        )
        st.download_button("⬇️ Λήψη εντολής προσανατολισμού για ChatGPT/Claude",orientation_doc,file_name=output_name,type="primary",use_container_width=True)
        if presentation == "Απλή και πρακτική":
            st.caption("Ανέβασε το Word στο ChatGPT ή στο Claude. Ζήτησε δύο αρχεία: το καθαρό Word του πελάτη και το εσωτερικό τεχνικό δελτίο ελέγχου.")
            paste_message = """Ακολούθησε πιστά τη δεσμευτική εντολή που περιλαμβάνεται στο έγγραφο και χρησιμοποίησε αποκλειστικά τα ελεγμένα τεχνικά δεδομένα που περιέχει. Μην επινοήσεις προσωπικά, επαγγελματικά ή ψυχολογικά στοιχεία.

Η επιλεγμένη παρουσίαση είναι «Απλή και πρακτική». Παράδωσε δύο χωριστά, ολοκληρωμένα αρχεία Word:
1. Το καθαρό παραδοτέο του πελάτη, χωρίς πλανήτες, Οίκους, όψεις, orb ή κατηγορίες βαρύτητας.
2. Το εσωτερικό τεχνικό δελτίο ελέγχου, με την πλήρη τεκμηρίωση που απαιτεί η δεσμευτική εντολή. Το δεύτερο αρχείο δεν παραδίδεται στον πελάτη.

Αν η υπηρεσία αφορά ενήλικα, εφάρμοσε υποχρεωτικά τον ειδικό Κανόνα 0Γ: το καθαρό παραδοτέο να είναι σύντομο, σε καθημερινή γλώσσα και χωρίς τους αναλυτικούς πίνακες, το εργασιακό περιβάλλον, τα επόμενα βήματα, το σχέδιο 8–12 εβδομάδων ή τις επαναλαμβανόμενες ενότητες της πλήρους έκδοσης. Το εσωτερικό τεχνικό δελτίο παραμένει αναλυτικό.

Το ανώνυμο πρότυπο σύντομης έκδοσης περιλαμβάνεται ήδη μέσα στο έγγραφο. Χρησιμοποίησέ το αποκλειστικά για τη δομή, το μήκος και την απλή γλώσσα· μην αντιγράψεις από αυτό περιεχόμενο ή συμπεράσματα.

Το καθαρό Word πρέπει να έχει λευκό φόντο και μαύρο κείμενο, όπως το πρότυπο. Μην χρησιμοποιήσεις highlight, χρωματιστό φόντο, σκιάσεις, έγχρωμα πλαίσια ή χρωματιστές λωρίδες. Η έμφαση να γίνεται μόνο με τίτλους, κουκκίδες και περιορισμένη έντονη γραφή.

Κάνε προσεκτικό αυτοέλεγχο πριν από την παράδοση. Ο πραγματικός validator θα εκτελεστεί στη συνέχεια μέσα στο AstroCheck Pro."""
        else:
            st.caption("Ανέβασε αυτό το ένα Word στο ChatGPT ή στο Claude και ζήτησε να ακολουθήσει τη δεσμευτική εντολή που περιέχει.")
            paste_message = """Ακολούθησε πιστά τη δεσμευτική εντολή που περιλαμβάνεται στο έγγραφο και χρησιμοποίησε αποκλειστικά τα ελεγμένα τεχνικά δεδομένα που περιέχει. Μην επινοήσεις προσωπικά, επαγγελματικά ή ψυχολογικά στοιχεία.

Η επιλεγμένη παρουσίαση είναι «Αναλυτική με αστρολογική τεκμηρίωση». Δημιούργησε ένα ολοκληρωμένο, καλαίσθητο αρχείο Word για τον πελάτη και συμπερίλαβε στο τέλος το τεχνικό παράρτημα που απαιτεί η δεσμευτική εντολή.

Κάνε προσεκτικό αυτοέλεγχο πριν από την παράδοση. Ο πραγματικός validator θα εκτελεστεί στη συνέχεια μέσα στο AstroCheck Pro."""

        if service == "Παιδί/έφηβος" and cyprus_school == "Ναι" and presentation == "Απλή και πρακτική":
            paste_message += """

Το παιδί/ο έφηβος φοιτά στο κυπριακό εκπαιδευτικό σύστημα. Στην απλή έκδοση πρόσθεσε σύντομη ενότητα «Πλαίσιο Εκπαιδευτικού Συστήματος (Κύπρος)» με τις υποενότητες «Τι ισχύει σήμερα στο σύστημα» και «Τι δείχνουν συμβολικά τα ταλέντα». Μην προσθέσεις χωριστές πανεπιστημιακές σπουδές/Τμήματα σε κάθε επαγγελματικό τομέα, ερωτήσεις συζήτησης, οδηγίες προς γονείς/εκπαιδευτικούς ή σχέδιο 8–12 εβδομάδων. Χρησιμοποίησε μόνο πρόσφατα επαληθευμένες επίσημες πληροφορίες για το εκπαιδευτικό σύστημα και μην κατατάξεις ή αποκλείσεις ΟΜΠ."""
        elif service == "Παιδί/έφηβος" and cyprus_school == "Ναι":
            paste_message += """

Το παιδί/ο έφηβος φοιτά στο κυπριακό εκπαιδευτικό σύστημα. Πρόσθεσε πριν από την «Τελική Σύνθεση» ξεχωριστή ενότητα «Πλαίσιο Εκπαιδευτικού Συστήματος (Κύπρος)». Διαχώρισε καθαρά το «Τι ισχύει σήμερα στο σύστημα» από το «Τι δείχνουν συμβολικά τα ταλέντα». Χρησιμοποίησε αποκλειστικά πρόσφατα επαληθευμένα επίσημα στοιχεία. Μην κατατάξεις ΟΜΠ χωρίς πραγματικά δεδομένα ενδιαφέροντος, σχολικής επίδοσης ή προτίμησης μαθημάτων και μην αποκλείσεις καμία ΟΜΠ ή εκπαιδευτική Κατεύθυνση. Σε καθέναν από τους 4–6 «Επαγγελματικούς Τομείς προς Διερεύνηση», πρόσθεσε μετά τα «Ενδεικτικά επαγγέλματα» τη χωριστή ετικέτα «Ενδεικτικές πανεπιστημιακές σπουδές/Τμήματα». Δώσε αντιπροσωπευτικές διαδρομές σπουδών Κύπρου και Ελλάδας που συνδέονται με τον συγκεκριμένο τομέα, βάσει του πιο πρόσφατου επίσημου Οδηγού Παγκύπριων Εξετάσεων Πρόσβασης. Μην συγχέεις επάγγελμα, πανεπιστημιακό Τμήμα και Πλαίσιο Πρόσβασης και μην παρουσιάζεις καμία αναφορά ως εγγύηση εισαγωγής ή αποκλεισμό άλλων επιλογών. Μην προσθέσεις χωριστή ενότητα «Επίσημες πηγές» στο καθαρό παραδοτέο του πελάτη· κατέγραψε τις πηγές μόνο στο εσωτερικό τεχνικό δελτίο ελέγχου."""
        elif service == "Παιδί/έφηβος":
            paste_message += """

Το παιδί/ο έφηβος δεν φοιτά στο κυπριακό εκπαιδευτικό σύστημα. Παράλειψε την ενότητα για τις ΟΜΠ και τις εκπαιδευτικές διαδρομές της Κύπρου και μην υποθέσεις άλλο εκπαιδευτικό σύστημα."""

        with st.expander("Έτοιμο μήνυμα για επικόλληση στο ChatGPT/Claude", expanded=True):
            st.code(paste_message, language=None)

        st.divider()
        orientation_result=st.file_uploader("Αποτέλεσμα επαγγελματικού προσανατολισμού (.docx)",type=['docx'],key=f"orientation_result_{st.session_state.uploader_gen}")
        orientation_audit = None
        if presentation == "Απλή και πρακτική":
            orientation_audit=st.file_uploader(
                "Εσωτερικό τεχνικό δελτίο ελέγχου (.docx) — δεν παραδίδεται στον πελάτη",
                type=['docx'],
                key=f"orientation_audit_{st.session_state.uploader_gen}",
            )
        ready_to_check = bool(orientation_result) and (
            presentation != "Απλή και πρακτική" or bool(orientation_audit)
        )
        if st.button("Έλεγχος επαγγελματικού προσανατολισμού",disabled=not ready_to_check,use_container_width=True):
            result_bytes=orientation_result.getvalue()
            result_text=docx_text(result_bytes)
            result_format_issues = simple_docx_format_issues(result_bytes)
            audit_bytes=orientation_audit.getvalue() if orientation_audit else None
            audit_text=docx_text(audit_bytes) if audit_bytes else None
            orientation_personal={"Όνομα": name_override or chart.name}
            check=validate_orientation(
                chart, result_text, orientation_personal, service,
                presentation_mode=presentation, audit_text=audit_text,
                cyprus_education=(cyprus_school == "Ναι"),
                format_issues=result_format_issues,
            )
            st.session_state.orientation_validation=check
            st.session_state.orientation_docx_bytes=result_bytes
            st.session_state.orientation_docx_name=orientation_result.name
            st.session_state.orientation_audit_docx_bytes=audit_bytes
        check=st.session_state.get('orientation_validation')
        if check:
            if check.ok:
                st.markdown(f'<div class="ok">{check.summary()}</div>',unsafe_allow_html=True)
                st.download_button("⬇️ Λήψη ελεγμένου επαγγελματικού προσανατολισμού",st.session_state.orientation_docx_bytes,file_name=st.session_state.orientation_docx_name,use_container_width=True)
            else:
                st.markdown(f'<div class="warn">⚠ {check.summary()}</div>',unsafe_allow_html=True)
                with st.expander("Λεπτομέρειες",expanded=True):
                    for line in check.details_lines(): st.write("•",line)
