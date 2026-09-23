"""
case_state.py
==============
Καθαρή λογική διαχείρισης της κατάστασης ενός "case" (μιας φοράς ελέγχου/
ανάλυσης ενός συγκεκριμένου ατόμου) στο AstroCheck Pro, χωρίς εξάρτηση από
το Streamlit runtime κατά την εκτέλεση των tests.

Γιατί εξήχθη από το app.py:
Το streamlit.testing.v1.AppTest (το επίσημο εργαλείο δοκιμών του Streamlit)
ΔΕΝ υποστηρίζει προσομοίωση αλληλεπίδρασης με st.file_uploader. Το πραγματικό
bug που διορθώθηκε εδώ (session-state διαρροή δεδομένων πελάτη κατά την
απευθείας αντικατάσταση PDF, χωρίς προηγούμενο πάτημα "Νέα ανάλυση") ζει
ακριβώς μέσα στο callback ενός file_uploader -- άρα δεν μπορούσε να ελεγχθεί
αξιόπιστα μέσω πλήρους προσομοίωσης UI.

Η λύση: η επιχειρησιακή λογική (ποια keys καθαρίζονται, πότε αυξάνεται το
uploader_gen, τι συμβαίνει σε επιτυχία/αποτυχία parsing) ζει εδώ, σε
συναρτήσεις που δέχονται ένα απλό `state` αντικείμενο (οτιδήποτε υποστηρίζει
attribute get/set και μέθοδο pop(key, default) -- ακριβώς η επιφάνεια του
st.session_state που χρησιμοποιείται). Το app.py καλεί αυτές τις συναρτήσεις
χωρίς όρισμα state (default: το πραγματικό st.session_state). Τα tests
περνάνε ένα ελαφρύ ψεύτικο state, χωρίς να χρειάζεται καθόλου Streamlit
runtime ή προσομοίωση file_uploader.
"""
from __future__ import annotations

# Keys που ανήκουν αποκλειστικά στον ΤΡΕΧΟΝΤΑ πελάτη/χάρτη και ΠΡΕΠΕΙ να
# καθαρίζονται τόσο στο κουμπί "Νέα ανάλυση" όσο και σε κάθε επιτυχημένη
# ανάγνωση ΝΕΟΥ PDF -- ανεξάρτητα από το ποιος δρόμος το πυροδότησε.
# ΔΕΝ περιλαμβάνει 'chart' και 'uploader_gen': αυτά τα διαχειρίζεται ρητά
# ο καλών (reset_case_state τα αφήνει σκόπιμα ανέγγιχτα).
CASE_STATE_KEYS = (
    'confirmed', 'name_override', 'profession', 'family', 'projects', 'habits',
    'experiences', 'language', 'pasted_analysis',
    'rewrite_validation', 'rewrite_docx_bytes', 'rewrite_docx_name',
    'orientation_validation', 'orientation_service', 'orientation_presentation',
    'orientation_cyprus_school', 'orientation_docx_bytes', 'orientation_docx_name',
    'orientation_audit_docx_bytes',
)


def _default_state():
    import streamlit as st
    return st.session_state


def reset_case_state(state=None) -> None:
    """Καθαρίζει ΟΛΑ τα δεδομένα του τρέχοντος πελάτη -- προσωπικό πλαίσιο,
    ανάλυση, αναδιατύπωση, προσανατολισμό. ΔΕΝ αγγίζει 'chart' ή
    'uploader_gen' -- αυτά τα αποφασίζει ρητά ο καλών (βλ. handle_pdf_upload
    και το κουμπί "Νέα ανάλυση" στο app.py).

    `state`: αντικείμενο με attribute get/set + pop(key, default). Όταν
    λείπει, χρησιμοποιείται αυτόματα το πραγματικό st.session_state (μόνο
    τότε γίνεται το `import streamlit`, ώστε τα tests να μην το χρειάζονται).
    """
    if state is None:
        state = _default_state()
    state.analysis = ''
    state.validation = None
    state.analysis_docx_bytes = None
    state.analysis_docx_name = ''
    for k in CASE_STATE_KEYS:
        state.pop(k, None)


def handle_pdf_upload(pdf_bytes: bytes, pdf_name: str, state=None, parse_fn=None):
    """Διαβάζει ένα Astrodienst PDF και, ΜΟΝΟ αν πετύχει το parsing,
    καθαρίζει την προηγούμενη περίπτωση (reset_case_state) και αποθηκεύει
    το νέο chart -- ώστε η απευθείας αντικατάσταση PDF (χωρίς προηγούμενο
    πάτημα "Νέα ανάλυση") να μην αφήνει πίσω όνομα, προσωπικό πλαίσιο ή
    παλιά rewrite/orientation bytes του προηγούμενου πελάτη.

    Αυξάνει επίσης το 'uploader_gen' κατά 1 σε επιτυχία, ώστε ΟΛΟΙ οι
    file_uploader της εφαρμογής (rewrite_docx_*, orientation_result_*,
    orientation_audit_*, analysis_docx_* -- όχι μόνο pdf/instructions/style)
    να ξαναδημιουργηθούν άδειοι στο επόμενο render, χωρίς να παραμένει
    επιλεγμένο ένα παλιό αρχείο σε κάποιο widget.

    Σε αποτυχία parsing, ΔΕΝ αγγίζεται καμία υπάρχουσα κατάσταση -- ένα
    λάθος ανέβασμα δεν πρέπει να διαγράψει μια ήδη έγκυρη περίπτωση.

    `parse_fn`: η συνάρτηση ανάγνωσης PDF (bytes, filename) -> Chart. Όταν
    λείπει, χρησιμοποιείται η πραγματική parser.parse_astrodienst_pdf. Τα
    tests περνάνε ένα ψεύτικο parse_fn ώστε να μη χρειάζονται πραγματικό
    Astrodienst PDF binary.

    Επιστρέφει (ok: bool, chart_or_None, error_or_None).
    """
    if state is None:
        state = _default_state()
    if parse_fn is None:
        from parser import parse_astrodienst_pdf as parse_fn

    try:
        new_chart = parse_fn(pdf_bytes, pdf_name)
    except Exception as e:
        return False, None, e

    reset_case_state(state)
    state.uploader_gen = getattr(state, 'uploader_gen', 0) + 1
    state.chart = new_chart
    return True, new_chart, None
