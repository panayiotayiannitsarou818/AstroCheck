"""Δείγματα κειμένου για τα tests του εντύπου πελάτη (όχι μέρος της εφαρμογής).

Ένα έντυπο που περνά τον έλεγχο χρειάζεται πλέον ουσιαστικό κείμενο σε κάθε
Οίκο και ενότητα, «Κεντρικό θέμα:» σε κάθε Οίκο και κατονομασία κάθε πλανήτη
στον Οίκο του. Εδώ φτιάχνονται τέτοια ουδέτερα κείμενα.
"""

import lexicon_en as EN

# Ένα διαφορετικό κείμενο για κάθε Οίκο: ο έλεγχος απορρίπτει πλέον την ίδια
# παράγραφο επαναλαμβανόμενη σε πολλούς Οίκους (κανόνας 9).
HOUSE_TEXTS_EL = [
    "Ο τρόπος που εμφανίζεσαι στους άλλους μπορεί να κρύβει περισσότερη ευαισθησία απ' όση δείχνεις. Όταν νιώθεις ασφαλής, η παρουσία σου γίνεται ζεστή και σταθερή.",
    "Η σχέση σου με την αξία σου μπορεί να περνά μέσα από όσα καταφέρνεις με τα χέρια σου. Μαθαίνεις σιγά σιγά ότι αξίζεις και όταν ξεκουράζεσαι.",
    "Στον τρόπο που μιλάς φαίνεται μια ανάγκη να σε καταλαβαίνουν σωστά. Οι κουβέντες με τα αδέλφια ή τους γείτονες σε βοηθούν να οργανώσεις τις σκέψεις σου.",
    "Το σπίτι για σένα λειτουργεί σαν καταφύγιο και σαν βάση για να ξαναβρίσκεις δυνάμεις. Οι οικογενειακές ρίζες σου δίνουν αντοχή, αλλά μερικές φορές και βάρος.",
    "Η χαρά σου ανθίζει όταν δημιουργείς κάτι δικό σου χωρίς να σε κρίνουν. Το παιχνίδι και η έκφραση είναι για σένα τρόποι να θυμάσαι ποιος είσαι.",
    "Στην καθημερινή δουλειά χρειάζεσαι ρυθμό που να σέβεται το σώμα σου. Μικρές σταθερές συνήθειες σε κρατούν πιο ήρεμο από μεγάλες αλλαγές της στιγμής.",
    "Στις στενές σχέσεις αναζητάς έναν σύντροφο που να σε βλέπει ως ίσο. Η συνεργασία σε ωριμάζει όταν μπορείς να ζητάς όσα θέλεις χωρίς ενοχή.",
    "Όσα μοιράζεσαι βαθιά με άλλους σε αγγίζουν έντονα και σε αλλάζουν. Η εμπιστοσύνη χτίζεται για σένα αργά, αλλά όταν δοθεί είναι γερή.",
    "Τα ταξίδια, οι σπουδές και οι μεγάλες ιδέες ανοίγουν τον ορίζοντά σου. Ψάχνεις ένα νόημα που να στέκει και στην πράξη, όχι μόνο στη θεωρία.",
    "Στον επαγγελματικό δρόμο θέλεις να αφήσεις ένα αποτύπωμα που να σου μοιάζει. Η αναγνώριση έχει σημασία, αλλά ακόμη περισσότερο η αίσθηση ότι κάνεις κάτι χρήσιμο.",
    "Οι φίλοι και οι ομάδες σού δίνουν έμπνευση για το μέλλον. Νιώθεις πιο δυνατός όταν μοιράζεσαι ένα κοινό όραμα με ανθρώπους που σε σέβονται.",
    "Ο εσωτερικός σου κόσμος χρειάζεται ησυχία για να ακουστεί. Στις στιγμές απόσυρσης βρίσκεις απαντήσεις που ο θόρυβος της μέρας συχνά σκεπάζει.",
]
HOUSE_TEXTS_EN = [
    "The way you appear to others may hide more sensitivity than you show. When you feel safe, your presence becomes warm and steady.",
    "Your sense of worth may pass through what you achieve with your own hands. You slowly learn that you are worthy even when you rest.",
    "In the way you speak there is a need to be understood correctly. Conversations with siblings or neighbours help you organise your thoughts.",
    "Home works for you as a refuge and as a base where you regain strength. Family roots give you endurance, but sometimes also weight.",
    "Your joy blossoms when you create something of your own without being judged. Play and expression are ways for you to remember who you are.",
    "In daily work you need a rhythm that respects your body. Small steady habits keep you calmer than big changes of the moment.",
    "In close bonds you look for a partner who sees you as an equal. Cooperation matures you when you can ask for what you want without guilt.",
    "What you share deeply with others touches you strongly and changes you. Trust is built slowly for you, but once given it is solid.",
    "Travel, study and big ideas open your horizon. You search for a meaning that holds up in practice, not only in theory.",
    "On your professional path you want to leave a mark that resembles you. Recognition matters, but even more the feeling that you do something useful.",
    "Friends and groups give you inspiration for the future. You feel stronger when you share a common vision with people who respect you.",
    "Your inner world needs quiet in order to be heard. In moments of retreat you find answers that the noise of the day often covers.",
]
FILLER_EL = (
    "Σε αυτό το πεδίο της ζωής σου μπορεί να χρειάζεσαι χρόνο για να εμπιστευτείς τον εαυτό σου. "
    "Η ώριμη έκφραση αυτής της δυναμικής φαίνεται όταν επιτρέπεις στον εαυτό σου να κινείται με "
    "υπομονή, να ακούει τις ανάγκες του και να δίνει χώρο σε ό,τι χρειάζεται φροντίδα. Το ζητούμενο "
    "εδώ είναι να βρεις ισορροπία ανάμεσα στην ανάγκη για ασφάλεια και στην επιθυμία να εξελιχθείς, "
    "χωρίς να πιέζεις τα πράγματα πριν ωριμάσουν μέσα σου."
)
FILLER_EN = (
    "In this area of your life you may need time to trust yourself. The mature expression of this "
    "dynamic appears when you allow yourself to move with patience, to listen to your needs and to "
    "give space to whatever needs care. The aim here is to find a balance between the need for "
    "security and the wish to grow, without pushing things before they have matured inside you."
)


def house_body(n, chart=None, lang="el") -> str:
    english = lang == "en"
    names = [
        (EN.en(p.name) if english else p.name)
        for p in (getattr(chart, "points", None) or [])
        if p.house == n and p.kind in ("planet", "node")
    ]
    intro = ""
    if names:
        joined = ", ".join(names)
        intro = (f"The themes of {joined} matter here. " if english else f"Εδώ έχουν βάρος: {joined}. ")
    theme = "Central theme: patience and trust." if english else "Κεντρικό θέμα: υπομονή και εμπιστοσύνη."
    text = (HOUSE_TEXTS_EN if english else HOUSE_TEXTS_EL)[n - 1]
    return f"{intro}{text}\n{theme}"


def section_body(lang="el") -> str:
    return FILLER_EN if lang == "en" else FILLER_EL


def houses_el(chart=None, heading_suffix="", extra_for=None) -> str:
    extra_for = extra_for or {}
    return "\n".join(
        f"{n}ος Οίκος{heading_suffix}\n{house_body(n, chart)}{extra_for.get(n, '')}" for n in range(1, 13)
    )


def houses_en(chart=None, extra_for=None) -> str:
    extra_for = extra_for or {}
    return "\n".join(
        f"{EN.house_heading(n)}\n{house_body(n, chart, 'en')}{extra_for.get(n, '')}" for n in range(1, 13)
    )
