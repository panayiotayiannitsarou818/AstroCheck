"""v19.4: πρόοδος ανά στάδιο και εκτίμηση χρόνου που απομένει.

Δεν χρησιμοποιεί σταθερή αντίστροφη μέτρηση: η διάρκεια εξαρτάται από τους
γύρους διόρθωσης. Η εκτίμηση βγαίνει από τις ΠΡΑΓΜΑΤΙΚΕΣ διάρκειες των
προηγούμενων αναλύσεων (αποθηκεύονται τοπικά) και διορθώνεται μετά από κάθε
γύρο. Χωρίς ιστορικό χρησιμοποιούνται προσεκτικές αρχικές τιμές.

Το module δεν εξαρτάται από το Streamlit, ώστε να ελέγχεται με tests.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Callable, Optional

STAGE_ANALYSIS = "Ανάλυση"
STAGE_REWRITE = "Τελικό έντυπο"

KIND_CREATE = "δημιουργία"
KIND_FIX = "διόρθωση"
KIND_POLISH = "γύρος ποιότητας"

# Αρχικές εκτιμήσεις σε δευτερόλεπτα, μέχρι να υπάρξουν πραγματικές μετρήσεις.
DEFAULT_SECONDS = {
    (STAGE_ANALYSIS, KIND_CREATE): 9 * 60,
    (STAGE_ANALYSIS, KIND_FIX): 7 * 60,
    (STAGE_ANALYSIS, KIND_POLISH): 6 * 60,
    (STAGE_REWRITE, KIND_CREATE): 5 * 60,
    (STAGE_REWRITE, KIND_FIX): 4 * 60,
    (STAGE_REWRITE, KIND_POLISH): 4 * 60,
}
DEFAULT_FIX_ROUNDS = 1.0  # αναμενόμενοι γύροι διόρθωσης ανά στάδιο
HISTORY_LIMIT = 30
TIMINGS_FILE = Path(__file__).resolve().parent / ".astrocheck_timings.json"

KEEP_PAGE_OPEN = (
    "⏳ Μην κλείσεις και μην ανανεώσεις αυτή τη σελίδα μέχρι να ολοκληρωθεί η διαδικασία — "
    "αλλιώς σταματά και θα χρειαστεί να ξεκινήσει από την αρχή. Μπορείς να αφήσεις την καρτέλα "
    "ανοιχτή και να κάνεις κάτι άλλο στο μεταξύ."
)


def _key(stage: str, kind: str) -> str:
    return f"{stage}|{kind}"


class TimingStore:
    """Πραγματικές διάρκειες γύρων και πλήθος διορθώσεων, σε αρχείο JSON.
    Κάθε αποτυχία ανάγνωσης/εγγραφής αγνοείται: η εκτίμηση απλώς γυρίζει στις
    αρχικές τιμές."""

    def __init__(self, path: Optional[Path] = TIMINGS_FILE):
        self.path = path
        self.data: dict = {}
        if path is not None:
            try:
                self.data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def _push(self, key: str, value: float) -> None:
        values = list(self.data.get(key, []))[-(HISTORY_LIMIT - 1):]
        values.append(round(float(value), 1))
        self.data[key] = values

    def record_round(self, stage: str, kind: str, seconds: float) -> None:
        if seconds > 0:
            self._push(_key(stage, kind), seconds)

    def record_fix_rounds(self, stage: str, count: int) -> None:
        self._push(_key(stage, "πλήθος διορθώσεων"), count)

    def seconds(self, stage: str, kind: str) -> float:
        values = self.data.get(_key(stage, kind))
        return float(median(values)) if values else float(DEFAULT_SECONDS[(stage, kind)])

    def fix_rounds(self, stage: str) -> float:
        values = self.data.get(_key(stage, "πλήθος διορθώσεων"))
        return float(median(values)) if values else DEFAULT_FIX_ROUNDS

    def save(self) -> None:
        if self.path is None:
            return
        try:
            Path(self.path).write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def expected_total(store: TimingStore, stages=(STAGE_ANALYSIS, STAGE_REWRITE)) -> float:
    return sum(
        store.seconds(s, KIND_CREATE) + store.fix_rounds(s) * store.seconds(s, KIND_FIX) for s in stages
    )


def minutes_text(seconds: float) -> str:
    m = max(1, math.ceil(seconds / 60))
    return "περίπου 1 λεπτό" if m == 1 else f"περίπου {m} λεπτά"


def range_text(store: TimingStore, stages=(STAGE_ANALYSIS, STAGE_REWRITE)) -> str:
    """«Συνήθως 15–30 λεπτά»: εύρος με περιθώριο, όχι υπόσχεση ακριβείας."""
    total = expected_total(store, stages)
    low = max(1, int(round(total * 0.7 / 60 / 5) * 5) or 1)
    high = max(low + 5, int(math.ceil(total * 1.4 / 60 / 5) * 5))
    return f"Συνήθως {low}–{high} λεπτά"


STEP_TEXT = {
    (STAGE_ANALYSIS, KIND_CREATE): "Γράφεται η ανάλυση των 12 Οίκων",
    (STAGE_ANALYSIS, KIND_FIX): "Έλεγχος και διόρθωση της ανάλυσης",
    (STAGE_REWRITE, KIND_CREATE): "Γράφεται το τελικό έντυπο",
    (STAGE_REWRITE, KIND_FIX): "Έλεγχος και διόρθωση του τελικού εντύπου",
}


@dataclass
class ProgressTracker:
    """Παρακολουθεί τους γύρους και δίνει: βήμα Χ από Υ, ποσοστό, χρόνο που απομένει."""

    store: TimingStore
    stages: tuple = (STAGE_ANALYSIS, STAGE_REWRITE)
    clock: Callable[[], float] = time.monotonic
    started: float = 0.0
    last: float = 0.0
    stage: str = ""
    fixes: dict = field(default_factory=dict)
    done: set = field(default_factory=set)  # στάδια που πέρασαν
    phase: str = KIND_CREATE  # τι γίνεται ΤΩΡΑ στο τρέχον στάδιο

    def __post_init__(self):
        self.started = self.last = self.clock()
        self.stage = self.stages[0]

    @property
    def total_steps(self) -> int:
        return 2 * len(self.stages)

    @property
    def step(self) -> int:
        index = self.stages.index(self.stage) if self.stage in self.stages else len(self.stages) - 1
        return 2 * index + (1 if self.phase == KIND_CREATE else 2)

    @property
    def step_text(self) -> str:
        return STEP_TEXT.get((self.stage, self.phase), "Ολοκλήρωση")

    def on_round(self, stage: str, rnd) -> None:
        now = self.clock()
        kind = getattr(rnd, "kind", KIND_CREATE)
        if kind not in (KIND_CREATE, KIND_FIX, KIND_POLISH):
            kind = KIND_FIX
        self.store.record_round(stage, kind, now - self.last)
        self.last = now
        self.stage = stage
        if kind == KIND_FIX:
            self.fixes[stage] = self.fixes.get(stage, 0) + 1
        if getattr(rnd, "ok", False):
            if stage not in self.done:  # ο γύρος ποιότητας δεν ξαναμετρά τις διορθώσεις
                self.store.record_fix_rounds(stage, self.fixes.get(stage, 0))
            self.done.add(stage)
            later = [s for s in self.stages if s not in self.done]
            if later:
                self.stage, self.phase = later[0], KIND_CREATE
            else:
                self.phase = "τέλος"
        else:
            self.phase = KIND_FIX

    def remaining_seconds(self) -> float:
        rest = 0.0
        for s in self.stages:
            if s in self.done:
                continue
            fixes_left = self.store.fix_rounds(s) - self.fixes.get(s, 0)
            if s == self.stage and self.phase == KIND_FIX:
                rest += self.store.seconds(s, KIND_FIX) * max(1.0, fixes_left)
            else:
                rest += self.store.seconds(s, KIND_CREATE) + self.store.seconds(s, KIND_FIX) * max(0.0, fixes_left)
        # αφαιρείται όσος χρόνος έχει ήδη περάσει μέσα στον τρέχοντα γύρο
        rest -= self.clock() - self.last
        return max(60.0, rest) if self.phase != "τέλος" else 0.0

    def fraction(self) -> float:
        elapsed = self.clock() - self.started
        remaining = self.remaining_seconds()
        if remaining <= 0:
            return 1.0
        return min(0.97, elapsed / (elapsed + remaining))

    def label(self) -> str:
        if self.phase == "τέλος":
            return "Ολοκληρώθηκε"
        return (
            f"Βήμα {self.step} από {self.total_steps}: {self.step_text}… "
            f"Απομένουν {minutes_text(self.remaining_seconds())}."
        )

    def finish(self) -> None:
        self.store.save()
