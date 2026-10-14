"""v19.4: πρόοδος ανά στάδιο, εκτίμηση χρόνου, μήνυμα «μην κλείσεις τη σελίδα»."""

from types import SimpleNamespace as R

import progress as P


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _tracker(tmp_path, stages=(P.STAGE_ANALYSIS, P.STAGE_REWRITE)):
    clock = Clock()
    store = P.TimingStore(tmp_path / "t.json")
    return P.ProgressTracker(store, stages, clock=clock), clock, store


def test_initial_label_shows_step_one_and_remaining_time(tmp_path):
    t, _, _ = _tracker(tmp_path)
    assert t.label().startswith("Βήμα 1 από 4: Γράφεται η ανάλυση των 12 Οίκων")
    assert "Απομένουν περίπου" in t.label()


def test_steps_advance_through_the_whole_run(tmp_path):
    t, clock, _ = _tracker(tmp_path)
    clock.t = 600
    t.on_round(P.STAGE_ANALYSIS, R(kind="δημιουργία", ok=False))
    assert t.step == 2 and "διόρθωση της ανάλυσης" in t.label()
    clock.t = 900
    t.on_round(P.STAGE_ANALYSIS, R(kind="διόρθωση", ok=True))
    assert t.step == 3 and "τελικό έντυπο" in t.label()
    clock.t = 1200
    t.on_round(P.STAGE_REWRITE, R(kind="δημιουργία", ok=True))
    assert t.label() == "Ολοκληρώθηκε" and t.remaining_seconds() == 0


def test_remaining_time_shrinks_and_progress_grows(tmp_path):
    t, clock, _ = _tracker(tmp_path)
    r0, f0 = t.remaining_seconds(), t.fraction()
    clock.t = 300
    r1, f1 = t.remaining_seconds(), t.fraction()
    assert r1 < r0 and f1 > f0
    assert t.fraction() < 1.0  # ποτέ 100% πριν τελειώσει


def test_estimate_never_reaches_zero_while_still_running(tmp_path):
    t, clock, _ = _tracker(tmp_path, (P.STAGE_ANALYSIS,))
    clock.t = 10_000  # πολύ περισσότερο από την εκτίμηση
    assert t.remaining_seconds() >= 60 and "Απομένουν περίπου 1 λεπτό" in t.label()


def test_real_durations_are_learned_and_used_next_time(tmp_path):
    t, clock, store = _tracker(tmp_path, (P.STAGE_ANALYSIS,))
    clock.t = 120  # η πραγματική δημιουργία κράτησε 2 λεπτά (αρχική εκτίμηση: 9)
    t.on_round(P.STAGE_ANALYSIS, R(kind="δημιουργία", ok=True))
    t.finish()
    again = P.TimingStore(tmp_path / "t.json")
    assert again.seconds(P.STAGE_ANALYSIS, "δημιουργία") == 120
    assert again.fix_rounds(P.STAGE_ANALYSIS) == 0


def test_quality_round_does_not_count_fixes_twice(tmp_path):
    t, clock, store = _tracker(tmp_path, (P.STAGE_ANALYSIS,))
    t.on_round(P.STAGE_ANALYSIS, R(kind="δημιουργία", ok=True))
    t.on_round(P.STAGE_ANALYSIS, R(kind="γύρος ποιότητας", ok=True))
    assert store.data["Ανάλυση|πλήθος διορθώσεων"] == [0]


def test_broken_timings_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "t.json"
    path.write_text("χαλασμένο", encoding="utf-8")
    store = P.TimingStore(path)
    assert store.seconds(P.STAGE_ANALYSIS, "δημιουργία") == P.DEFAULT_SECONDS[(P.STAGE_ANALYSIS, "δημιουργία")]


def test_range_text_gives_a_margin():
    text = P.range_text(P.TimingStore(None))
    assert text.startswith("Συνήθως ") and "–" in text and text.endswith("λεπτά")


def test_keep_page_open_message():
    assert "Μην κλείσεις" in P.KEEP_PAGE_OPEN and "ανανεώσεις" in P.KEEP_PAGE_OPEN


def test_progress_panel_renders_in_the_app():
    from streamlit.testing.v1 import AppTest

    def page():
        import streamlit as st
        from types import SimpleNamespace as R

        import progress as P

        store = P.TimingStore(None)
        st.warning(P.KEEP_PAGE_OPEN)
        tracker = P.ProgressTracker(store, (P.STAGE_ANALYSIS, P.STAGE_REWRITE))
        bar = st.progress(0.02, text=tracker.label())
        tracker.on_round(P.STAGE_ANALYSIS, R(kind="δημιουργία", ok=False))
        bar.progress(tracker.fraction(), text=tracker.label())

    at = AppTest.from_function(page).run()
    assert not at.exception
    assert "Μην κλείσεις" in at.warning[0].value
