"""Τα κουμπιά «Συνέχεια στην …» αλλάζουν πραγματικά καρτέλα.

Αιτία του σφάλματος: οι καρτέλες είχαν on_change="ignore" (προεπιλογή), οπότε
ΔΕΝ παρακολουθούνταν ως widget. Η τιμή st.session_state.main_tab άλλαζε, αλλά
η οθόνη δεν τη λάμβανε ποτέ. Με on_change="rerun" το tab_container αποκτά id
widget και η ενεργή καρτέλα ακολουθεί το session_state.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from parser import parse_astrodienst_pdf

APP = str(Path(__file__).parent / "app.py")


def _tab_container_protos(node, found):
    proto = getattr(node, "proto", None)
    if proto is not None and str(proto).startswith("tab_container"):
        found.append(proto.tab_container)
    children = getattr(node, "children", None)
    if isinstance(children, dict):
        children = children.values()
    for child in children or []:
        _tab_container_protos(child, found)
    return found


def _app_with_chart():
    path = Path(__file__).parent / "fixtures" / "astro_paradeigma_2.pdf"
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.session_state["chart"] = parse_astrodienst_pdf(path.read_bytes(), path.name)
    at.run()
    return at


def test_tabs_are_tracked_widgets():
    at = _app_with_chart()
    containers = _tab_container_protos(at._tree, [])
    assert containers and containers[0].id, "οι καρτέλες πρέπει να έχουν id widget (on_change='rerun')"


def test_continue_button_switches_to_analysis_tab():
    at = _app_with_chart()
    button = next(b for b in at.button if "Συνέχεια στην Ανάλυση" in b.label)
    button.click().run()
    assert not at.exception
    assert at.session_state["main_tab"] == "2 · Ανάλυση & έλεγχος"
    containers = _tab_container_protos(at._tree, [])
    assert containers[0].default_tab_index == 1
