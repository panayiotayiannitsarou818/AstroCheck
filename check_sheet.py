"""Ανακατασκευή χάρτη από το «Δελτίο ελέγχου» (AstroCheck_Elegxos_kai_Odigies).

Χρήση: μόνο για δοκιμές με πραγματικά έγγραφα όταν το PDF του Astrodienst δεν
είναι διαθέσιμο. Το Δελτίο παράγεται από το ίδιο το πρόγραμμα μετά τον έλεγχο
του PDF, άρα περιέχει όλα τα ελεγμένα δεδομένα: θέσεις, ακμές και όψεις.
Στην κανονική ροή της εφαρμογής ο χάρτης διαβάζεται πάντα από το PDF.
"""

import re

from astrology import absolute
from models import Aspect, Chart, Point
from validation_patterns import _ASPECT_FORMS, _NAME_FORMS, _WEIGHT_FORMS

_POS = r"(\S+)\s+(\d{1,2})°(\d{1,2})′(\d{1,2})″"
_KIND = {"Ωροσκόπος": "angle", "Μεσουράνημα": "angle", "Βόρειος Δεσμός": "node", "Νότιος Δεσμός": "node"}


def _orb(text: str) -> float:
    d, m = re.match(r"(\d{1,2})°(\d{1,2})′", text).groups()
    return int(d) + int(m) / 60


def chart_from_check_sheet(text: str) -> Chart:
    names = sorted(_NAME_FORMS, key=len, reverse=True)
    name_alt = "|".join(re.escape(n) for n in names)
    points = []
    for m in re.finditer(
        rf"^({name_alt}) \| {_POS}( ανάδρομος)? \| (\d{{1,2}}|—) \|", text, re.MULTILINE
    ):
        name, sign, d, mi, s, retro, house = m.groups()
        points.append(
            Point(
                name, name, sign, int(d), int(mi), int(s),
                absolute(sign, int(d), int(mi), int(s)),
                int(house) if house.isdigit() else None,
                bool(retro), _KIND.get(name, "planet"),
            )
        )
    cusps = []
    for m in re.finditer(rf"^(\d{{1,2}})ος ΟΙΚΟΣ\nΑκμή και έκταση: {_POS}", text, re.MULTILINE):
        n, sign, d, mi, s = m.groups()
        cusps.append(
            Point(f"H{n}", f"{n}ος Οίκος", sign, int(d), int(mi), int(s),
                  absolute(sign, int(d), int(mi), int(s)), kind="cusp")
        )
    aspect_alt = "|".join(re.escape(a) for a in sorted(_ASPECT_FORMS, key=len, reverse=True))
    weight_alt = "|".join(re.escape(w) for w in sorted(_WEIGHT_FORMS, key=len, reverse=True))
    aspects, seen = [], set()
    for m in re.finditer(
        rf"({name_alt})–({name_alt})(?::| \|)? ({aspect_alt})(?:, orb | \| )(\d{{1,2}}°\d{{2}}′)(?:, | \| )({weight_alt})",
        text,
    ):
        first, second, kind, orb, weight = m.groups()
        key = frozenset((first, second))
        if key in seen:
            continue
        seen.add(key)
        source = (
            "Μαθηματική παραγωγή από τον άξονα Βόρειου/Νότιου Δεσμού"
            if "Νότιος Δεσμός" in key
            else "Πίνακας Astrodienst"
        )
        aspects.append(Aspect(first, second, kind, _orb(orb), orb, weight, source, None))
    name = re.search(r"^Όνομα: (.+)$", text, re.MULTILINE)
    if len(points) < 13 or len(cusps) != 12 or not aspects:
        raise ValueError("Το Δελτίο ελέγχου δεν περιέχει πλήρη δεδομένα χάρτη.")
    return Chart(name=name.group(1) if name else "", house_system="Placidus",
                 points=points, cusps=cusps, aspects=aspects)
