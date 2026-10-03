"""Ο πλήρης έλεγχος της τεχνικής ανάλυσης (validate_analysis).

Μέρος του validator (βλ. validator.py για το ιστορικό και τη συνολική περιγραφή)."""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from validation_patterns import (
    REQUIRED_SECTIONS,
    _HOUSE_PATTERNS,
    _HOUSE_PATTERNS_ALT,
    _HOUSE_WORD_PATTERNS,
    _find_appendix,
    _has_section,
    _name_pattern,
    _normalize_prime_marks,
)
from validation_aspects import (
    _check_aspects_present,
    _co_occurs_with_orb,
    _contradicts_aspect,
    _dedupe_aspects,
    _mandatory_aspects,
    _strict_occurrence_errors,
    _aspect_claim_problems,
    _stray_technical_values,
    _malformed_aspect_rows,
)
from validation_structure import (
    _box_ruler_text,
    _house_segments,
    _involved_points,
    _location_claim_errors,
    _ruler_errors,
    _ruler_names_in_body,
    _sign_claim_errors,
    _unauthorized_personal_claims,
)


@dataclass
class ValidationResult:
    ok: bool
    missing_houses: list = field(default_factory=list)
    missing_aspects: list = field(default_factory=list)  # εντελώς απούσες, πουθενά στο κείμενο
    suspect_aspects: list = field(default_factory=list)  # ονόματα υπάρχουν, orb όχι κοντά
    missing_from_appendix: list = field(default_factory=list)
    missing_sections: list = field(default_factory=list)
    missing_per_house: list = field(default_factory=list)  # (house_number, aspect) -- κανόνας 6Β
    wrong_aspect_type: list = field(default_factory=list)
    wrong_weight: list = field(default_factory=list)
    inconsistent_ruler_box: list = field(
        default_factory=list
    )  # (house_number, expected_names, box_text)
    wrong_house_claims: list = field(default_factory=list)
    unauthorized_personal_claims: list = field(default_factory=list)
    wrong_sign_claims: list = field(default_factory=list)  # (σημείο, δηλωμένο, σωστό, πλαίσιο)
    # v4
    wrong_ruler_claims: list = field(default_factory=list)  # (Οίκος, δηλωμένος, αναμενόμενος, πού)
    missing_ruler_box: list = field(default_factory=list)  # Οίκοι χωρίς «Κυβερνήτης:»
    undeclared_aspects: list = field(default_factory=list)  # (Α, Β, τύπος, απόσπασμα)
    # v7: γνωστό ζεύγος, αλλά η ΣΥΓΚΕΚΡΙΜΕΝΗ δήλωση έχει λάθος τύπο/orb/βαρύτητα
    aspect_claim_mismatches: list = field(default_factory=list)  # (όψη, διαφορά, απόσπασμα)
    # v9: αριθμός orb εκτός δομημένης γραμμής (Odigies v6, κανόνας 5)
    stray_technical_values: list = field(default_factory=list)  # (τιμή, απόσπασμα)
    # v10: γραμμή πίνακα που μοιάζει με γραμμή όψης αλλά δεν διαβάζεται πλήρως
    malformed_aspect_rows: list = field(default_factory=list)  # (λόγος, γραμμή)

    def summary(self) -> str:
        if self.ok:
            return (
                "✓ Ο μηχανικός έλεγχος πέρασε: όλα τα υποχρεωτικά στοιχεία εντοπίστηκαν, σε κάθε Οίκο "
                "που έπρεπε, και συμφωνούν με τα ελεγμένα δεδομένα. Ελέγχεται η συνέπεια με τα "
                "δεδομένα, όχι η ποιότητα της ερμηνείας."
            )
        parts = []
        if self.missing_houses:
            parts.append(
                f"{len(self.missing_houses)} Οίκοι δεν εντοπίστηκαν ({', '.join(map(str, self.missing_houses))})"
            )
        if self.missing_aspects:
            parts.append(
                f"{len(self.missing_aspects)} υποχρεωτικές όψεις (τετράγωνα/αντιθέσεις/σύνοδοι με γωνία) λείπουν εντελώς"
            )
        if self.suspect_aspects:
            parts.append(f"{len(self.suspect_aspects)} όψεις με ύποπτο ή απόν orb")
        if self.missing_from_appendix:
            parts.append(f"{len(self.missing_from_appendix)} όψεις δεν εντοπίστηκαν στο Παράρτημα")
        if self.missing_sections:
            parts.append(f"λείπουν οι ενότητες: {', '.join(self.missing_sections)}")
        if self.missing_per_house:
            parts.append(
                f"{len(self.missing_per_house)} όψεις κυβερνήτη λείπουν από συγκεκριμένο Οίκο (κανόνας 6Β)"
            )
        if self.wrong_aspect_type:
            parts.append(f"{len(self.wrong_aspect_type)} όψεις έχουν λανθασμένο ή απόντα τύπο")
        if self.wrong_weight:
            parts.append(
                f"{len(self.wrong_weight)} όψεις έχουν λανθασμένη ή απούσα κατηγορία βαρύτητας"
            )
        if self.inconsistent_ruler_box:
            parts.append(
                f"{len(self.inconsistent_ruler_box)} πλαίσια σύνοψης έχουν κυβερνήτη που δεν συμφωνεί με το κυρίως κείμενο του ίδιου Οίκου"
            )
        if self.wrong_house_claims:
            parts.append(
                f"{len(self.wrong_house_claims)} λανθασμένες δηλώσεις τοποθέτησης πλανήτη σε Οίκο"
            )
        if self.unauthorized_personal_claims:
            parts.append(
                f"{len(self.unauthorized_personal_claims)} μη εξουσιοδοτημένες προσωπικές αναφορές"
            )
        if self.wrong_sign_claims:
            parts.append(f"{len(self.wrong_sign_claims)} λανθασμένες δηλώσεις ζωδίου")
        if self.wrong_ruler_claims:
            parts.append(
                f"{len(self.wrong_ruler_claims)} δηλώσεις κυβερνήτη δεν αντιστοιχούν στο ζώδιο της ακμής"
            )
        if self.missing_ruler_box:
            parts.append(
                f"{len(self.missing_ruler_box)} Οίκοι χωρίς γραμμή «Κυβερνήτης:» στο πλαίσιο σύνοψης"
            )
        if self.malformed_aspect_rows:
            parts.append(f"{len(self.malformed_aspect_rows)} γραμμές όψεων δεν διαβάζονται πλήρως")
        if self.stray_technical_values:
            parts.append(
                f"{len(self.stray_technical_values)} αριθμοί orb εκτός δομημένης γραμμής όψης"
            )
        if self.aspect_claim_mismatches:
            parts.append(
                f"{len(self.aspect_claim_mismatches)} δηλώσεις όψης διαφέρουν από τον χάρτη σε τύπο, orb ή βαρύτητα"
            )
        if self.undeclared_aspects:
            parts.append(
                f"{len(self.undeclared_aspects)} όψεις δηλώνονται στο κείμενο αλλά δεν υπάρχουν στον ελεγμένο χάρτη"
            )
        return "Η ανάλυση δεν ολοκληρώθηκε: " + "· ".join(parts) + "."

    def details_lines(self) -> list[str]:
        lines = []
        for n in self.missing_houses:
            lines.append(f"Οίκος {n}: δεν βρέθηκε επικεφαλίδα στο κείμενο.")
        for a in self.missing_aspects:
            lines.append(
                f"{a.first}–{a.second} ({a.aspect}, orb {a.orb_text}): δεν αναφέρεται πουθενά."
            )
        for a in self.suspect_aspects:
            lines.append(
                f"{a.first}–{a.second}: αναφέρονται και τα δύο ονόματα, αλλά όχι το orb {a.orb_text} κοντά τους -- έλεγξε χειροκίνητα."
            )
        for a in self.missing_from_appendix:
            lines.append(
                f"{a.first}–{a.second}: δεν εντοπίστηκε μέσα στο Παράρτημα Επιβεβαιωμένων Όψεων."
            )
        for s in self.missing_sections:
            lines.append(f"Λείπει η υποχρεωτική ενότητα: «{s}».")
        for house_n, a in self.missing_per_house:
            lines.append(
                f"Οίκος {house_n}: η όψη {a.first}–{a.second} (orb {a.orb_text}) δεν αναφέρεται μέσα σε αυτόν τον Οίκο, παρότι εμπλέκει πλανήτη/κυβερνήτη του."
            )
        for a in self.wrong_aspect_type:
            lines.append(
                f"{a.first}–{a.second}: αναμενόταν «{a.aspect}» μαζί με orb {a.orb_text}, αλλά ο σωστός τύπος δεν εντοπίστηκε κοντά στο ζεύγος."
            )
        for a in self.wrong_weight:
            lines.append(
                f"{a.first}–{a.second}: αναμενόταν βαρύτητα «{a.weight}» μαζί με orb {a.orb_text}, αλλά δεν εντοπίστηκε κοντά στο ζεύγος."
            )
        for house_n, expected, box_text in self.inconsistent_ruler_box:
            lines.append(
                f"Οίκος {house_n}: το κυρίως κείμενο ονομάζει κυβερνήτη {', '.join(expected)}, αλλά το πλαίσιο σύνοψης λέει «{box_text}» -- πιθανή αντιγραφή από άλλον Οίκο."
            )
        for point_name, claimed, expected, snippet in self.wrong_house_claims:
            lines.append(
                f"Λανθασμένη τοποθέτηση — {point_name}: το κείμενο τον/την δηλώνει στον {claimed}ο Οίκο, ενώ τα ελεγμένα δεδομένα δίνουν {expected}ο Οίκο. Σημείο: {snippet}"
            )
        for category, snippet in self.unauthorized_personal_claims:
            lines.append(f"Μη δηλωμένο προσωπικό στοιχείο ({category}): «{snippet}»")
        for point_name, claimed, expected, snippet in self.wrong_sign_claims:
            lines.append(
                f"Λανθασμένο ζώδιο — {point_name}: το κείμενο γράφει {claimed}, ενώ τα ελεγμένα δεδομένα δίνουν {expected}. Σημείο: {snippet}"
            )
        for house_n, claimed, expected, where in self.wrong_ruler_claims:
            lines.append(
                f"Οίκος {house_n}: το {where} δηλώνει κυβερνήτη {claimed}, ενώ από το ζώδιο της ακμής είναι {expected}."
            )
        for house_n in self.missing_ruler_box:
            lines.append(
                f"Οίκος {house_n}: λείπει (ή δεν ονομάζει πλανήτη) η γραμμή «Κυβερνήτης:» του πλαισίου σύνοψης."
            )
        for reason, row in self.malformed_aspect_rows:
            lines.append(
                f"Μη αναγνώσιμη γραμμή όψης — {reason}. Κάθε γραμμή όψης: «Α–Β | Τύπος | orb X°YY′ | Κατηγορία». Γραμμή: «{row}»"
            )
        for value, snip in self.stray_technical_values:
            lines.append(
                f"Τεχνικό στοιχείο εκτός δομημένης γραμμής — {value}: οι αριθμοί orb γράφονται μόνο στη μορφή «Α–Β Τύπος (orb X°YY′, Κατηγορία)», σε δική τους γραμμή. Σημείο: «{snip}»"
            )
        for a, diff, snip in self.aspect_claim_mismatches:
            lines.append(
                f"Λάθος δήλωση όψης — {a.first}–{a.second}: {diff} (ελεγμένα: {a.aspect}, orb {a.orb_text}, {a.weight}). Σημείο: «{snip}»"
            )
        for a, b, t, snip in self.undeclared_aspects:
            lines.append(
                f"Αναφορά σε όψη που δεν υπάρχει στον χάρτη — {a}–{b} ({t}). Σημείο: «{snip}»"
            )
        return lines


def validate_analysis(chart, analysis_text: str, personal: dict | None = None) -> ValidationResult:
    text = _normalize_prime_marks(analysis_text)

    missing_houses = []
    for n in range(1, 13):
        if (
            _HOUSE_PATTERNS[n - 1].search(text)
            or _HOUSE_PATTERNS_ALT[n - 1].search(text)
            or _HOUSE_WORD_PATTERNS[n - 1].search(text)
        ):
            continue
        missing_houses.append(n)

    # v2: mandatory = τετράγωνα/αντιθέσεις (όπως πριν) ΣΥΝ κάθε σύνοδο όπου
    # συμμετέχει γωνία (Ωροσκόπος/Μεσουράνημα) -- πριν αγνοούνταν εντελώς.
    mandatory = _mandatory_aspects(chart)
    missing_aspects, suspect_aspects, wrong_aspect_type, wrong_weight = _check_aspects_present(
        text, mandatory
    )

    appendix_text = _find_appendix(text)
    missing_from_appendix = []
    if appendix_text:
        # ίδια βοηθητική με το validate_rewrite() (βλ. _check_aspects_present) --
        # εδώ διατηρείται σκόπιμα σαν ενιαία λίστα αποτυχίας (ανεξαρτήτως
        # missing/suspect/wrong_type/wrong_weight), όπως ήταν πάντα το πεδίο
        # missing_from_appendix του ValidationResult.
        m, s, wt, ww = _check_aspects_present(appendix_text, chart.aspects)
        missing_from_appendix = _dedupe_aspects(m, s, wt, ww)

    missing_sections = [section for section in REQUIRED_SECTIONS if not _has_section(text, section)]

    # v2: έλεγχος ανά Οίκο (κανόνας 6Β) -- κάθε mandatory όψη πρέπει να
    # εμφανίζεται ΜΕΣΑ στο τμήμα κειμένου κάθε Οίκου όπου εμπλέκεται
    # πλανήτης/κυβερνήτης/γωνία του, όχι απλώς κάπου στο έγγραφο.
    missing_per_house = []
    segments = _house_segments(text)
    for house_number in range(1, 13):
        segment = segments.get(house_number)
        if not segment:
            continue  # ήδη καταγράφηκε στο missing_houses
        involved = _involved_points(chart, house_number)
        for a in mandatory:
            if a.first not in involved and a.second not in involved:
                continue
            co_occurs, orb_ok, type_ok, weight_ok = _co_occurs_with_orb(
                segment, a.first, a.second, a.orb_text, a.aspect, a.weight
            )
            if not (co_occurs and orb_ok):
                missing_per_house.append((house_number, a))

    # v3: κάθε Οίκος πρέπει να δηλώνει τον ίδιο κυβερνήτη και στο κυρίως
    # κείμενο και στο πλαίσιο σύνοψής του -- βλ. σημείωση v3 στην κορυφή
    # του module.
    inconsistent_ruler_box = []
    for house_number in range(1, 13):
        segment = segments.get(house_number)
        if not segment:
            continue  # ήδη καταγράφηκε στο missing_houses
        expected = _ruler_names_in_body(segment)
        if not expected:
            continue  # δεν εντοπίστηκε δηλωμένος κυβερνήτης στο κείμενο -- τίποτα να συγκρίνουμε
        box_text = _box_ruler_text(segment)
        if box_text is None:
            continue  # δεν υπάρχει καθόλου πλαίσιο σύνοψης -- άλλο θέμα, όχι ασυνέπεια
        if not all(re.search(_name_pattern(name), box_text, re.IGNORECASE) for name in expected):
            inconsistent_ruler_box.append((house_number, expected, box_text))

    wrong_house_claims = _location_claim_errors(chart, text)
    wrong_sign_claims = _sign_claim_errors(chart, text)
    wrong_ruler_claims, missing_ruler_box = _ruler_errors(chart, segments)
    undeclared_aspects, aspect_claim_mismatches = _aspect_claim_problems(chart, text)
    stray_technical_values = _stray_technical_values(text)
    malformed_aspect_rows = _malformed_aspect_rows(text)
    unauthorized_personal_claims = _unauthorized_personal_claims(personal, text)

    # Έλεγχος συνέπειας ΟΛΩΝ των αναφερόμενων όψεων, όχι μόνο των
    # υποχρεωτικών τετραγώνων/αντιθέσεων. Έτσι εντοπίζεται, για παράδειγμα,
    # λάθος κατηγορία σε σύνοδο Ήλιου–Άρη ή λάθος τύπος σε τελική σύνθεση.
    for a in chart.aspects:
        bad_type, bad_weight = _contradicts_aspect(text, a)
        strict_bad_type, strict_bad_weight = _strict_occurrence_errors(text, a)
        bad_type = bad_type or strict_bad_type
        bad_weight = bad_weight or strict_bad_weight
        if bad_type and a not in wrong_aspect_type:
            wrong_aspect_type.append(a)
        if bad_weight and a not in wrong_weight:
            wrong_weight.append(a)

    ok = not (
        missing_houses
        or missing_aspects
        or suspect_aspects
        or missing_from_appendix
        or missing_sections
        or missing_per_house
        or wrong_aspect_type
        or wrong_weight
        or inconsistent_ruler_box
        or wrong_house_claims
        or unauthorized_personal_claims
        or wrong_sign_claims
        or wrong_ruler_claims
        or missing_ruler_box
        or undeclared_aspects
        or aspect_claim_mismatches
        or stray_technical_values
        or malformed_aspect_rows
    )
    return ValidationResult(
        ok,
        missing_houses,
        missing_aspects,
        suspect_aspects,
        missing_from_appendix,
        missing_sections,
        missing_per_house,
        wrong_aspect_type,
        wrong_weight,
        inconsistent_ruler_box,
        wrong_house_claims,
        unauthorized_personal_claims,
        wrong_sign_claims=wrong_sign_claims,
        wrong_ruler_claims=wrong_ruler_claims,
        missing_ruler_box=missing_ruler_box,
        undeclared_aspects=undeclared_aspects,
        aspect_claim_mismatches=aspect_claim_mismatches,
        stray_technical_values=stray_technical_values,
        malformed_aspect_rows=malformed_aspect_rows,
    )
