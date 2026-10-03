from astrology import RULERS, SIGNS, axis_activation_note, degree_theory, orb_to_text
import lexicon_en as EN


def is_english(language) -> bool:
    return str(language or "").strip().lower() in ("αγγλικά", "english", "en")


def english_terminology_block(chart) -> str:
    """Δεσμευτικό αγγλικό λεξιλόγιο για αγγλική ανάλυση.

    Τα ελεγμένα δεδομένα της εντολής είναι στα ελληνικά. Χωρίς αυτό το μπλοκ
    το μοντέλο μεταφράζει ελεύθερα (π.χ. «Close/strong» αντί «Tight/strong»)
    και ο validator δεν μπορεί να επαληθεύσει τίποτα. Οι όροι προέρχονται
    από το lexicon_en.py -- το ίδιο αρχείο που χρησιμοποιεί ο validator.
    """

    def table(mapping):
        return "\n".join(f"- {gr} → {en}" for gr, en in mapping.items())

    appendix = (
        "\n".join(
            f"- {EN.en(a.first)}–{EN.en(a.second)} | {EN.en(a.aspect)} | orb {a.orb_text} | {EN.en(a.weight)}"
            for a in chart.aspects
        )
        or "- (no aspects)"
    )
    headings = ", ".join(EN.house_heading(n) for n in range(1, 13))
    sections = "\n".join(f"- {en}" for en in EN.SECTION_TITLES.values())
    return f"""
ENGLISH OUTPUT — MANDATORY TERMINOLOGY (ΔΕΣΜΕΥΤΙΚΟ)
Η τελική ανάλυση γράφεται ΟΛΟΚΛΗΡΗ στα αγγλικά. Τα ελεγμένα δεδομένα παρακάτω είναι στα ελληνικά· μετάφρασέ τα ΑΠΟΚΛΕΙΣΤΙΚΑ με τους παρακάτω όρους, λέξη προς λέξη, χωρίς συνώνυμα. Ο μηχανικός έλεγχος αναγνωρίζει μόνο αυτούς τους όρους.

Points:
{table(EN.POINT_NAMES)}

Signs:
{table(EN.SIGN_NAMES)}

Aspect types:
{table(EN.ASPECT_NAMES)}

Weight categories (copy exactly, including the slash):
{table(EN.WEIGHT_NAMES)}

Rules for English output:
1. Each House heading on its own line, exactly: {headings}.
2. STRUCTURED FORMAT (rule 5 of the v6 instructions): at the start of each House, write its aspects one per line, exactly as: <Point>–<Point> <aspect type> (orb X°YY′, <weight category>). Keep the symbols ° and ′ exactly as in the data. Orb numbers appear ONLY in these lines and in the Appendix — never inside prose, summary boxes or final sections; the prose interprets the aspects without numbers. Placements in signs (e.g. 12°30′ Leo) and distances from a cusp are allowed as usual.
3. In each House, name the ruler with the sentence «The modern ruler is <Planet>.» and, where a traditional ruler exists, «The traditional ruler is <Planet>.»
4. Summary box of each House, one label per line: «Key strength:», «Key challenge:», «Ruler:», «Final conclusion:». The «Ruler:» line is mandatory, names the modern ruler first and then the traditional ruler where one exists, and must agree with the main text of the same House.
5. State placements explicitly: «<Planet> is in the <N>th House», «<Planet> in <Sign>».
6. The mandatory in-House subsections are titled «Synthesis with the rest of the chart» and «Practical application».
7. Final sections, each title on its own line, exactly:
{sections}
8. The IC/Descendant axis notes in brackets are translated as «Imum Coeli (IC)» and «Descendant» — they are not separate aspects.

APPENDIX OF CONFIRMED ASPECTS — ENGLISH (single source; copy each line exactly):
{appendix}
"""


def fmt(p):
    rx = " ανάδρομος" if p.retrograde else ""
    return f"{p.sign} {p.degree}°{p.minute:02d}′{p.second:02d}″{rx}"


def ruler_block(chart, cusp):
    modern, traditional = RULERS[cusp.sign]

    def describe(name, label):
        ruler = next((p for p in chart.points if p.name == name), None)
        if not ruler:
            return f"{label}: {name} — δεν εντοπίστηκε στα δεδομένα."
        aspects = [a for a in chart.aspects if ruler.name in (a.first, a.second)]
        aspect_text = (
            "; ".join(
                f"{a.first}–{a.second} {a.aspect}, orb {a.orb_text}, {a.weight}" for a in aspects
            )
            or "καμία επιβεβαιωμένη όψη"
        )
        return (
            f"{label}: {name}. Θέση: {fmt(ruler)}, {ruler.house}ος Οίκος. " f"Όψεις: {aspect_text}."
        )

    blocks = [describe(modern, "Σύγχρονος/κύριος κυβερνήτης")]
    if traditional and traditional != modern:
        blocks.append(describe(traditional, "Παραδοσιακός κυβερνήτης"))
    return "\n".join(blocks)


def intercepted_signs(cusp, nxt) -> list[str]:
    """Ζώδια που βρίσκονται ΟΛΟΚΛΗΡΑ μέσα στον Οίκο, χωρίς να πέφτουν σε
    καμία ακμή (εγκλωβισμένα ζώδια)."""
    span = (nxt.absolute - cusp.absolute) % 360
    found = []
    for index, sign in enumerate(SIGNS):
        offset = (index * 30 - cusp.absolute) % 360
        if 0 < offset and offset + 30 <= span:
            found.append(sign)
    return found


def _intercepted_note(cusp, nxt) -> str:
    signs = intercepted_signs(cusp, nxt)
    if not signs:
        return ""
    names = " και ".join(signs)
    if len(signs) == 1:
        head, body = (
            "Εγκλωβισμένο ζώδιο",
            "βρίσκεται ολόκληρο μέσα στον Οίκο, χωρίς να πέφτει σε ακμή",
        )
    else:
        head, body = (
            "Εγκλωβισμένα ζώδια",
            "βρίσκονται ολόκληρα μέσα στον Οίκο, χωρίς να πέφτουν σε ακμή",
        )
    return (
        f"{head}: {names} — {body}. "
        "Ανέφερέ το στο «Πού βρίσκεται ο Οίκος» ως συμπληρωματική χροιά του Οίκου. "
        "Ο κυβερνήτης του Οίκου παραμένει ΜΟΝΟ ο κυβερνήτης του ζωδίου της ακμής· "
        "ο κυβερνήτης του εγκλωβισμένου ζωδίου δεν γίνεται κυβερνήτης του Οίκου.\n"
    )


def house_section(chart, number):
    cusp = chart.cusps[number - 1]
    nxt = chart.cusps[number % 12]
    planets = [p for p in chart.points if p.house == number and p.kind in ("planet", "node")]
    modern_ruler, traditional_ruler = RULERS[cusp.sign]
    involved = {p.name for p in planets}
    involved.add(modern_ruler)
    if traditional_ruler:
        involved.add(traditional_ruler)
    # Ο Οίκος 1 και ο Οίκος 7 μοιράζονται τον άξονα Ωροσκόπου/Δύσης· ο Οίκος 4
    # και ο Οίκος 10 τον άξονα Πυθμένα Ουρανού/Μεσουρανήματος. Καμία όψη προς
    # αυτά τα σημεία δεν πρέπει να εμφανίζεται ΜΟΝΟ στον Οίκο όπου τυχαίνει να
    # βρίσκεται ο άλλος πλανήτης -- πρέπει να εμφανίζεται και εδώ, στον Οίκο
    # που το ίδιο το σημείο ορίζει. (Έτσι διορθώνεται η περίπτωση Χείρωνα: η
    # σύνοδός του με τον Ωροσκόπο πρέπει να αναλυθεί και στον 1ο και στον 7ο
    # Οίκο, όχι μόνο στον 12ο όπου τυχαίνει να κατοικεί ο Χείρωνας.)
    if number in (1, 7):
        involved.add("Ωροσκόπος")
    if number in (4, 10):
        involved.add("Μεσουράνημα")
    aspects = [a for a in chart.aspects if a.first in involved or a.second in involved]
    hard = [a for a in aspects if a.aspect in ("Τετράγωνο", "Αντίθεση")]
    other = [a for a in aspects if a not in hard]
    near = []
    for p in planets:
        distance = (nxt.absolute - p.absolute) % 360
        if distance <= 5:
            near.append(
                f"{p.name}: τεχνικά στον {number}ο, απόσταση {orb_to_text(distance)} από την επόμενη ακμή· μπορεί συμπληρωματικά να επηρεάζει τον {number%12+1}ο."
            )
    plist = (
        "\n".join(f"- {p.name}: {fmt(p)} · {degree_theory(p)}" for p in planets)
        or "- Κανένας πλανήτης."
    )

    def alines(items):
        lines = []
        for a in items:
            note = axis_activation_note(a)
            suffix = f" [{note}]" if note else ""
            lines.append(
                f"- {a.first}–{a.second}: {a.aspect}, orb {a.orb_text}, {a.weight}, πηγή: {a.source}{suffix}"
            )
        return "\n".join(lines) or "- Καμία."

    return f"""{number}ος ΟΙΚΟΣ
Ακμή και έκταση: {fmt(cusp)} → {fmt(nxt)}.
{_intercepted_note(cusp, nxt)}Πλανήτες/σημεία:
{plist}
Κύριος κυβερνήτης:
{ruler_block(chart,cusp)}
Πλανήτες κοντά σε επόμενη ακμή:
{chr(10).join('- '+x for x in near) if near else '- Κανένας σε απόσταση έως 5°.'}
ΥΠΟΧΡΕΩΤΙΚΑ τετράγωνα και αντιθέσεις πλανητών και κυβερνητών:
{alines(hard)}
Άλλες επιβεβαιωμένες κύριες όψεις:
{alines(other)}

Στη συγγραφή αυτού του Οίκου συμπερίλαβε υποχρεωτικά: «Σύνθεση με τον υπόλοιπο χάρτη», «Η πρακτική εφαρμογή» και πλαίσιο σύνοψης με Βασική δύναμη, Βασική πρόκληση, Κυβερνήτη και Τελικό συμπέρασμα."""


def build_master_prompt(
    chart,
    personal,
    language,
    instructions_text,
    style_text,
    instructions_name="Ενσωματωμένες οδηγίες v6",
    style_name="Ενσωματωμένος καθαρός οδηγός ύφους",
):
    display_name = chart.name
    aspect_appendix = (
        "\n".join(
            f"- {a.first}–{a.second}: {a.aspect}, orb {a.orb_text}, {a.weight}, {a.source}"
            for a in chart.aspects
        )
        or "- Δεν αναγνωρίστηκαν όψεις. Σταμάτησε και ζήτησε έλεγχο."
    )
    houses = "\n\n".join(house_section(chart, i) for i in range(1, 13))
    english_block = english_terminology_block(chart) if is_english(language) else ""
    return f"""ΔΕΣΜΕΥΤΙΚΗ ΕΝΤΟΛΗ
Χρησιμοποίησε το «{instructions_name}» ως δεσμευτική προδιαγραφή και το «{style_name}» αποκλειστικά ως πρότυπο ύφους, βάθους, δομής και μορφοποίησης. Όλα τα αστρολογικά δεδομένα προέρχονται αποκλειστικά από το νέο PDF και τον παρακάτω ελεγμένο πίνακα. Μην μεταφέρεις δεδομένα ή προσωπικές πληροφορίες από το πρότυπο.

ΑΠΑΡΑΒΑΤΟ ΟΡΙΟ ΠΗΓΩΝ
Ο οδηγός ύφους δεν αποτελεί πηγή δεδομένων ή ερμηνευτικών συμπερασμάτων. Σε περίπτωση σύγκρουσης υπερισχύουν οι οδηγίες v6 και τα ελεγμένα δεδομένα του νέου χάρτη. Απαγορεύεται επίσης να χρησιμοποιήσεις μνήμη, προηγούμενες συνομιλίες ή εξωτερική γνώση για προσωπικά γεγονότα του ατόμου.

Γλώσσα τελικού Word: {language}.
Όνομα: {display_name}
Ημερομηνία: {chart.date} · Ώρα: {chart.time} · Τόπος: {chart.place}
Σύστημα Οίκων: {chart.house_system}
{english_block}
ΥΠΟΧΡΕΩΤΙΚΟΙ ΚΑΝΟΝΕΣ
1. Το όνομα του PDF επαρκεί για την ανάλυση. Προχώρησε χωρίς ερώτηση για προσωπικό πλαίσιο. Μην επινοήσεις προσωπικά γεγονότα.
1Α. Απαγορεύεται να παρουσιάσεις ως γεγονός συγκεκριμένο επάγγελμα, σπουδές, οικογενειακή κατάσταση, παιδιά, έργα, στόχους, συνήθειες ή εμπειρίες που δεν δίνονται στην τρέχουσα πηγή, ακόμη κι αν τα γνωρίζεις από προηγούμενη συνομιλία.
2. Μην παραλείψεις κανένα τετράγωνο ή αντίθεση του Astrodienst, ακόμη και όταν είναι πολύ πλατύ/δευτερεύον.
3. Η ίδια όψη πρέπει να έχει παντού το ίδιο orb και την ίδια κατηγορία.
3Α. Αντέγραψε ακριβώς από τα ελεγμένα δεδομένα και τα τρία πεδία κάθε όψης: ΤΥΠΟ ΟΨΗΣ, ORB και ΚΑΤΗΓΟΡΙΑ ΒΑΡΥΤΗΤΑΣ. Απαγορεύεται να μετατρέψεις αντίθεση σε τετράγωνο ή να αλλάξεις «Πλατιά αλλά έγκυρη» σε «Πολύ πλατιά/δευτερεύουσα», ακόμη και σε συνθετική ή τελική ενότητα.
3Β. ΔΟΜΗΜΕΝΗ ΜΟΡΦΗ (κανόνας 5 των οδηγιών v6): στην αρχή κάθε Οίκου γράψε τις όψεις του, μία ανά γραμμή, ακριβώς ως «Ήλιος–Σελήνη Τετράγωνο (orb 1°13′, Στενή/ισχυρή)». Αριθμοί orb γράφονται ΜΟΝΟ σε αυτές τις γραμμές και στο Παράρτημα — ποτέ μέσα σε πρόζα, σε πλαίσιο σύνοψης ή σε τελικές ενότητες. Η πρόζα ερμηνεύει τις όψεις χωρίς αριθμούς. Θέσεις σε ζώδιο (π.χ. 12°30′ Λέοντα) και αποστάσεις από ακμή επιτρέπονται κανονικά.
3Γ. ΚΥΒΕΡΝΗΤΕΣ (κανόνας 3): στο πλαίσιο σύνοψης κάθε Οίκου η γραμμή «Κυβερνήτης: <σύγχρονος>, <παραδοσιακός>» είναι υποχρεωτική, με τον σύγχρονο πρώτο (ο παραδοσιακός μόνο όπου υπάρχει). Στο κυρίως κείμενο ονόμασε ρητά τον κύριο κυβερνήτη και, όπου υπάρχει, τον παραδοσιακό.
4. Χρησιμοποίησε προσεκτική, πιθανική, μη μοιρολατρική και μη διαγνωστική γλώσσα.
5. Η Θεωρία των Μοιρών είναι μόνο συμπληρωματική και ακολουθεί ζώδιο, Οίκο, όψεις και κυβερνήτη.
6. Μετά τις δομημένες γραμμές όψεων, κάθε Οίκος να είναι συνεχές συνθετικό κείμενο και όχι ασύνδετη λίστα.
7. Όταν μια όψη αφορά τον Ωροσκόπο ή το Μεσουράνημα και έχει σημείωση σε αγκύλες [...], ενσωμάτωσε τη σημασία της -- ότι ενεργοποιείται ταυτόχρονα το απέναντι σημείο του άξονα (Δύση/Πυθμένας Ουρανού). ΜΗΝ τη γράψεις ως δεύτερη, ανεξάρτητη όψη με δικό της orb· είναι η ίδια όψη, από την άλλη άκρη του άξονα.

ΕΛΕΓΜΕΝΑ ΔΕΔΟΜΕΝΑ ΑΝΑ ΟΙΚΟ
{houses}

ΤΕΛΙΚΕΣ ΥΠΟΧΡΕΩΤΙΚΕΣ ΕΝΟΤΗΤΕΣ
- Τελική συνθετική εικόνα.
- Συμβολική κατεύθυνση εξέλιξης: Βόρειος/Νότιος Δεσμός, κυβερνήτης Βόρειου Δεσμού, επιβεβαιωμένες όψεις και πρακτική έκφραση.
- Προτάσεις προσωπικής ανάπτυξης και υποστήριξης, πρακτικές και μη διαγνωστικές.
- Παράρτημα επιβεβαιωμένων όψεων.
- Δεύτερος μαθηματικός, γλωσσικός και οπτικός έλεγχος πριν από την παράδοση.
- Στον δεύτερο έλεγχο σύγκρινε λέξη προς λέξη κάθε αναφερόμενη όψη με το Παράρτημα: ίδιο ζεύγος, ίδιος τύπος, ίδιο orb και ίδια κατηγορία βαρύτητας. Αν υπάρχει διαφορά, διόρθωσέ την πριν παραδώσεις.

ΠΑΡΑΡΤΗΜΑ ΕΠΙΒΕΒΑΙΩΜΕΝΩΝ ΟΨΕΩΝ — ΜΟΝΑΔΙΚΗ ΠΗΓΗ
{aspect_appendix}

ΜΟΡΦΟΠΟΙΗΣΗ
Παράδωσε καλαίσθητο Word με τίτλο, υπότιτλο, μεθοδολογία, βασικά δεδομένα, αρίθμηση σελίδων και κάθε Οίκο κατά προτίμηση σε νέα σελίδα. Κράτησε κάθε πλαίσιο σύνοψης ολόκληρο στην ίδια σελίδα.

================ ΠΛΗΡΕΙΣ ΔΕΣΜΕΥΤΙΚΕΣ ΟΔΗΓΙΕΣ v6 ================
{instructions_text}
================ ΤΕΛΟΣ ΟΔΗΓΙΩΝ v6 ================

================ ΚΑΘΑΡΟΣ ΟΔΗΓΟΣ ΥΦΟΥΣ — ΟΧΙ ΠΗΓΗ ΔΕΔΟΜΕΝΩΝ ================
{style_text}
================ ΤΕΛΟΣ ΟΔΗΓΟΥ ΥΦΟΥΣ ================"""
