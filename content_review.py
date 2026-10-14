"""v19: δεύτερος έλεγχος περιεχομένου με ΤΝ.

Ο κώδικας ελέγχει δεδομένα και δομή (validator). Αυτός ο έλεγχος διαβάζει το
ΝΟΗΜΑ των προτάσεων με λίγους σαφείς κανόνες, αντί για ατελείωτες λίστες
λέξεων: διάγνωση, βέβαιη πρόβλεψη, ο χάρτης ως «απόδειξη» καταλληλότητας,
επινοημένα προσωπικά στοιχεία, ερμηνεία εκτός πλαισίου Οίκου — και στο τελικό
έντυπο, απώλεια βασικής ερμηνείας της πηγής ή νέος ισχυρισμός.

Τρέχει ΜΟΝΟ όταν ο μηχανικός έλεγχος έχει ήδη περάσει (εξοικονόμηση κόστους).
Επιστρέφει ανά εύρημα: πρόταση, κανόνα, λόγο, διόρθωση. Τα «σοβαρά» ευρήματα
κλειδώνουν και πηγαίνουν στον κύκλο διόρθωσης· τα «ήπια» γίνονται παρατηρήσεις
για τον γύρο ποιότητας. Αν ο ίδιος ο έλεγχος αποτύχει (σφάλμα, μη αναγνώσιμη
απάντηση), ΔΕΝ κλειδώνει: εμφανίζεται παρατήρηση ότι δεν ολοκληρώθηκε.

Δεν είναι αλάνθαστος. Για να μην «κολλάει» ο κύκλος σε φανταστικά ευρήματα,
ένα σοβαρό εύρημα κλειδώνει μόνο αν η πρόταση που παραθέτει υπάρχει πράγματι
στο κείμενο (ή, για παράλειψη, στην πηγή).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from house_framework import framework_block

KIND_ANALYSIS = "analysis"
KIND_REWRITE = "rewrite"

SEVERE = "σοβαρό"
MILD = "ήπιο"
MAX_ISSUES = 15  # όσα ζητάμε από τον ελεγκτή
# v19.3: όσα ευρήματα κι αν επιστραφούν εξετάζονται ΟΛΑ (κανένα δεν αγνοείται)·
# πάνω από αυτό το όριο η απάντηση θεωρείται μη έγκυρη και ζητείται νέα.
MAX_ISSUES_ACCEPTED = 60
SEVERITY_VALUES = {"σοβαρό": "σοβαρό", "severe": "σοβαρό", "ήπιο": "ήπιο", "mild": "ήπιο"}
RULES_ANALYSIS = {1, 2, 3, 4, 5}
RULES_REWRITE = {1, 2, 3, 4, 5, 6, 7}
# Εκτίμηση εξόδου (tokens, μαζί με τη «σκέψη») ενός ελέγχου, πριν υπάρξει μέτρηση.
REVIEW_OUTPUT_ESTIMATE = 8_000
REVIEW_ATTEMPTS = 3  # v19.2: προσπάθειες πριν θεωρηθεί ότι ο έλεγχος απέτυχε
BUDGET_REASON = "δεν επαρκεί το όριο κόστους"
# Παρατήρηση που ΔΕΝ στέλνεται στον γύρο ποιότητας (δεν διορθώνεται με αλλαγή κειμένου).
REVIEW_FAILED_PREFIX = "Ο έλεγχος περιεχομένου με ΤΝ δεν ολοκληρώθηκε"

DEFAULT_REVIEW_MODELS = {"Claude": "claude-sonnet-5-5", "OpenAI": ""}  # "" = ίδιο με το κύριο
REVIEW_EFFORT = "medium"

_RULES_COMMON = """1. ΔΙΑΓΝΩΣΗ: αποδίδεται στο άτομο πάθηση, διαταραχή, σύμπτωμα, φάρμακο ή θεραπεία (σωματική ή ψυχική), με οποιαδήποτε διατύπωση. Επιτρέπονται: αρνήσεις («όχι διάγνωση»), ρητά συμβολική χρήση («πληγή» του Χείρωνα ως σύμβολο), γενική σύσταση να μιλήσει με επαγγελματία.
2. ΒΕΒΑΙΗ ΠΡΟΒΛΕΨΗ: μελλοντικό γεγονός παρουσιάζεται ως βέβαιο, ακόμη και χωρίς λέξη βεβαιότητας («θα αποκτήσεις περιουσία», «όταν μεγαλώσεις θα πετύχεις»). Επιτρέπονται τάσεις με «μπορεί», «ενδέχεται», «ίσως».
3. ΑΠΟΔΕΙΞΗ ΚΑΤΑΛΛΗΛΟΤΗΤΑΣ: ο χάρτης παρουσιάζεται ως απόδειξη ταλέντου ή ικανότητας («ο χάρτης αποδεικνύει…»), ή ορίζεται ποιο επάγγελμα «πρέπει» / «δεν πρέπει» να ακολουθήσει το άτομο, ή ποιο είναι «το σωστό» γι' αυτό.
4. ΕΠΙΝΟΗΜΕΝΟ ΠΡΟΣΩΠΙΚΟ ΣΤΟΙΧΕΙΟ: δηλώνεται ως γεγονός κάτι για τη ζωή του ατόμου που δεν δόθηκε (γονείς, παιδική ηλικία, σχέσεις, παιδιά, επάγγελμα, σπουδές, εμπειρίες, χαρακτήρας ως αμετάβλητο γεγονός). Για το άτομο δόθηκαν ΜΟΝΟ τα αρχικά του και ο χάρτης.
5. ΕΚΤΟΣ ΠΛΑΙΣΙΟΥ ΟΙΚΟΥ: ερμηνεία που περνά τα όρια του πλαισίου του Οίκου (π.χ. θάνατος ή χειρουργείο στον 8ο, νοσοκομεία ή φυλακές στον 12ο, ασθένειες στον 6ο, διαζύγιο στον 7ο)."""

_RULES_REWRITE = """6. ΑΠΩΛΕΙΑ ΒΑΣΙΚΗΣ ΕΡΜΗΝΕΙΑΣ: μια κεντρική ερμηνεία ενός Οίκου της ελεγμένης πηγής λείπει εντελώς από το έντυπο ή έχει αντιστραφεί. Στο πεδίο "sentence" παράθεσε την πρόταση της ΠΗΓΗΣ. Σοβαρό μόνο για κεντρικές ερμηνείες· για δευτερεύουσες, ήπιο.
7. ΝΕΟΣ ΙΣΧΥΡΙΣΜΟΣ: το έντυπο προσθέτει αστρολογικό ή προσωπικό συμπέρασμα που δεν υπάρχει στην πηγή."""

_FORMAT = """ΜΟΡΦΗ ΑΠΑΝΤΗΣΗΣ — ΜΟΝΟ JSON, χωρίς άλλο κείμενο:
{"issues": [{"sentence": "<ακριβές απόσπασμα, αυτολεξεί>", "rule": <αριθμός κανόνα>, "severity": "σοβαρό" ή "ήπιο", "reason": "<σύντομα γιατί>", "fix": "<πώς να ξαναγραφτεί>"}]}
Αν δεν υπάρχει παραβίαση: {"issues": []}
ΟΛΑ τα πεδία είναι υποχρεωτικά σε κάθε εύρημα· "rule" είναι ακέραιος αριθμός κανόνα· "severity" είναι ακριβώς "σοβαρό" ή "ήπιο".

Ανέφερε ΜΟΝΟ σαφείς παραβιάσεις των κανόνων — όχι ύφος, όχι προτιμήσεις, όχι αστρολογική ακρίβεια (τα δεδομένα έχουν ήδη ελεγχθεί από πρόγραμμα). Το πολύ {max} ευρήματα. Παράθεσε το απόσπασμα ΑΥΤΟΛΕΞΕΙ, ώστε να βρίσκεται στο κείμενο."""


def build_review_prompt(text: str, kind: str = KIND_ANALYSIS, source: str = "") -> str:
    what = (
        "την τεχνική αστρολογική ανάλυση των 12 Οίκων"
        if kind == KIND_ANALYSIS
        else "το τελικό έντυπο πελάτη, σε σύγκριση με την ελεγμένη τεχνική ανάλυση (πηγή)"
    )
    rules = _RULES_COMMON + ("\n" + _RULES_REWRITE if kind == KIND_REWRITE else "")
    parts = [
        f"Είσαι ελεγκτής περιεχομένου του AstroCheck Pro. Έλεγξε {what} ΜΟΝΟ με τους παρακάτω κανόνες.",
        "=== ΚΑΝΟΝΕΣ ===",
        rules,
        "=== " + framework_block(),
        "=== " + _FORMAT.replace("{max}", str(MAX_ISSUES)),
    ]
    if kind == KIND_REWRITE and source:
        parts += ["=== ΕΛΕΓΜΕΝΗ ΤΕΧΝΙΚΗ ΑΝΑΛΥΣΗ (ΠΗΓΗ) ===", source.strip()]
    parts += ["=== ΚΕΙΜΕΝΟ ΠΡΟΣ ΕΛΕΓΧΟ ===", text.strip()]
    return "\n\n".join(parts)


@dataclass
class Issue:
    sentence: str
    rule: str
    severity: str
    reason: str
    fix: str
    verified: bool = True

    @property
    def blocking(self) -> bool:
        # v19.2: κάθε σοβαρό εύρημα κλειδώνει (ασφαλής αποτυχία). Ένα σοβαρό
        # εύρημα που δεν εντοπίστηκε ελέγχεται πρώτα ΞΑΝΑ (βλ. with_content_review).
        return self.severity == SEVERE

    def line(self) -> str:
        where = "" if self.verified else " (η πρόταση δεν εντοπίστηκε αυτολεξεί· έλεγξε το σημείο που περιγράφεται)"
        return (
            f"Έλεγχος περιεχομένου (κανόνας {self.rule}) — {self.reason}. Πρόταση: «{self.sentence}»{where}. "
            f"Διόρθωση: {self.fix}"
        )


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_review(raw: str, kind: str = KIND_ANALYSIS) -> Optional[list[Issue]]:
    """Λίστα ευρημάτων, ή None αν η απάντηση δεν ακολουθεί ΑΥΣΤΗΡΑ το σχήμα.

    v19.3 — αυστηρό σχήμα: κάθε εύρημα είναι αντικείμενο με ΥΠΟΧΡΕΩΤΙΚΑ πεδία
    sentence, reason, fix (μη κενά κείμενα), rule (ακέραιος από τους κανόνες του
    ελέγχου) και severity («σοβαρό» ή «ήπιο»). Αρκεί ένα λάθος για να απορριφθεί
    όλη η απάντηση και να ζητηθεί νέα. Εξετάζονται ΟΛΑ τα ευρήματα."""
    if raw is None:
        return None
    m = _JSON_BLOCK.search(str(raw))
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    items = data.get("issues") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > MAX_ISSUES_ACCEPTED:
        return None
    allowed_rules = RULES_REWRITE if kind == KIND_REWRITE else RULES_ANALYSIS
    issues = []
    for it in items:
        if not isinstance(it, dict):
            return None
        fields = {}
        for key in ("sentence", "reason", "fix"):
            value = it.get(key)
            if not isinstance(value, str) or not value.strip():
                return None
            fields[key] = " ".join(value.split())
        rule = it.get("rule")
        if isinstance(rule, bool):
            return None
        if isinstance(rule, str) and rule.strip().isdigit():
            rule = int(rule.strip())
        if not isinstance(rule, int) or rule not in allowed_rules:
            return None
        severity = it.get("severity")
        if not isinstance(severity, str) or severity.strip().lower() not in SEVERITY_VALUES:
            return None
        issues.append(
            Issue(
                fields["sentence"][:300],
                str(rule),
                SEVERITY_VALUES[severity.strip().lower()],
                fields["reason"][:300],
                fields["fix"][:300],
            )
        )
    return issues


def _norm(text: str) -> str:
    return re.sub(r"[«»\"'“”‘’]", "", " ".join(str(text).split())).lower()


_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
_SPLIT = re.compile(r"(?<=[.!;;?·])\s+|\n+")
FUZZY_MATCH = 0.6  # κοινές λέξεις / λέξεις του αποσπάσματος


def _found(quote: str, where: str) -> bool:
    """Αυτολεξεί, ή σχεδόν αυτολεξεί (το μοντέλο άλλαξε λίγες λέξεις)."""
    needle = _norm(quote)
    if not needle:
        return False
    if needle[:80] in _norm(where):
        return True
    q = set(w.lower() for w in _WORDS.findall(quote))
    if len(q) < 3:
        return False
    for sentence in _SPLIT.split(where or ""):
        words = set(w.lower() for w in _WORDS.findall(sentence))
        if words and len(q & words) / len(q) >= FUZZY_MATCH:
            return True
    return False


def verify_issues(issues: list[Issue], text: str, source: str = "") -> list[Issue]:
    """Σημειώνει αν το απόσπασμα κάθε ευρήματος εντοπίζεται στο κείμενο
    (κανόνας 6: στην πηγή)."""
    for issue in issues:
        issue.verified = _found(issue.sentence, source if issue.rule == "6" else text)
    return issues


class ReviewedResult:
    """Το αποτέλεσμα του μηχανικού ελέγχου ΣΥΝ τα ευρήματα του ελέγχου περιεχομένου.
    Όλα τα υπόλοιπα πεδία προωθούνται στο αρχικό αποτέλεσμα."""

    def __init__(self, base, issues: list[Issue] | None = None, failed: str = ""):
        self.base = base
        self.content_issues = list(issues or [])
        self.review_failed = failed

    def __getattr__(self, name):
        return getattr(self.base, name)

    @property
    def blocking_issues(self) -> list[Issue]:
        return [i for i in self.content_issues if i.blocking]

    @property
    def budget_exhausted(self) -> bool:
        return self.review_failed == BUDGET_REASON

    @property
    def review_incomplete(self) -> bool:
        """v19.2: ο έλεγχος περιεχομένου δεν ολοκληρώθηκε -> το κείμενο ΔΕΝ περνά."""
        return bool(self.review_failed)

    @property
    def ok(self) -> bool:
        return bool(self.base.ok) and not self.blocking_issues and not self.review_incomplete

    @property
    def warnings(self) -> list:
        notes = list(getattr(self.base, "warnings", None) or [])
        notes += [i.line() for i in self.content_issues if not i.blocking]
        return notes

    def summary(self) -> str:
        if not self.base.ok:
            return self.base.summary()
        if self.review_incomplete:
            return (
                f"{REVIEW_FAILED_PREFIX} ({self.review_failed}): ο έλεγχος δεδομένων και δομής πέρασε, "
                "αλλά το κείμενο ΔΕΝ θεωρείται ελεγμένο χωρίς τον έλεγχο περιεχομένου. Πάτα ξανά για νέα προσπάθεια."
            )
        if self.blocking_issues:
            return (
                f"Ο έλεγχος δεδομένων και δομής πέρασε, αλλά ο έλεγχος περιεχομένου βρήκε "
                f"{len(self.blocking_issues)} σοβαρά ζητήματα (διάγνωση, βέβαιη πρόβλεψη, επινοημένο στοιχείο "
                "ή απώλεια νοήματος)."
            )
        return self.base.summary().replace(
            "ασφαλούς γλώσσας", "ασφαλούς γλώσσας και τον έλεγχο περιεχομένου με ΤΝ", 1
        ) if not self.review_failed else self.base.summary()

    def details_lines(self) -> list[str]:
        lines = list(self.base.details_lines()) + [i.line() for i in self.blocking_issues]
        if self.review_incomplete:
            lines.append(
                f"{REVIEW_FAILED_PREFIX} ({self.review_failed}) — το κείμενο δεν θεωρείται ελεγμένο."
            )
        return lines


def _key(issue: Issue) -> str:
    return _norm(issue.sentence)[:80]


def with_content_review(
    validate: Callable[[str], object],
    complete: Callable[[str, str, str], str],
    api_key: str,
    model: str,
    kind: str = KIND_ANALYSIS,
    source: str = "",
    usage=None,
    max_cost_usd: Optional[float] = None,
) -> Callable[[str], object]:
    """Τυλίγει έναν μηχανικό έλεγχο με τον έλεγχο περιεχομένου.

    Ασφαλής αποτυχία (v19.2): χωρίς έγκυρη απάντηση μετά από REVIEW_ATTEMPTS
    προσπάθειες, το κείμενο ΔΕΝ περνά.
    v19.3:
    - Ο επανέλεγχος εξετάζει ΜΟΝΟ τα αμφίβολα ευρήματα: τα σοβαρά ευρήματα που
      εντοπίστηκαν στο κείμενο ΚΡΑΤΙΟΥΝΤΑΙ, ό,τι κι αν απαντήσει ο επανέλεγχος.
    - Πριν από ΚΑΘΕ κλήση του ελεγκτή (και τις επαναλήψεις) ελέγχεται το όριο
      κόστους· αν δεν φτάνει, ο έλεγχος δεν γίνεται και το κείμενο δεν περνά."""

    def _no_budget(prompt) -> bool:
        if not max_cost_usd or usage is None:
            return False
        estimate = usage.estimate_review_usd(prompt, model, REVIEW_OUTPUT_ESTIMATE)
        return estimate is not None and usage.spent_usd + estimate > max_cost_usd

    def _one_review(prompt):
        """(ευρήματα ή None, σφάλμα)"""
        if _no_budget(prompt):
            return None, BUDGET_REASON
        try:
            raw = complete(api_key, prompt, model)
        except Exception as exc:
            if usage is not None:
                usage.add_failure(exc, model, main=False)
            return None, type(exc).__name__
        if usage is not None:
            usage.add(raw, model, main=False)
        issues = parse_review(raw, kind)
        return issues, ("" if issues is not None else "μη έγκυρη απάντηση")

    def _review(prompt):
        attempts, error = 0, ""
        while attempts < REVIEW_ATTEMPTS:
            attempts += 1
            issues, error = _one_review(prompt)
            if issues is not None or error == BUDGET_REASON:
                return issues, error
        return None, error

    def _validate(text: str):
        base = validate(text)
        if not base.ok:
            return base  # πρώτα διορθώνονται τα δεδομένα· ο έλεγχος ΤΝ δεν χρειάζεται ακόμη
        prompt = build_review_prompt(text, kind, source)
        issues, error = _review(prompt)
        if issues is None:
            return ReviewedResult(base, [], failed=error or "άγνωστο σφάλμα")
        verify_issues(issues, text, source)
        doubtful = [i for i in issues if i.severity == SEVERE and not i.verified]
        if doubtful:
            kept = [i for i in issues if not (i.severity == SEVERE and not i.verified)]
            again, error = _review(prompt)
            if again is None:
                # ο επανέλεγχος απέτυχε: κρατιούνται ΟΛΑ (και τα αμφίβολα) -- ασφαλής αποτυχία
                return ReviewedResult(base, issues, failed=error or "άγνωστο σφάλμα")
            verify_issues(again, text, source)
            seen = {_key(i) for i in kept}
            issues = kept + [i for i in again if _key(i) not in seen]
        return ReviewedResult(base, issues)

    return _validate


def review_model_for(provider: str, main_model: str, configured: str = "") -> str:
    return configured or DEFAULT_REVIEW_MODELS.get(provider) or main_model
