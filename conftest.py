"""Κοινές ρυθμίσεις δοκιμών.

v18: ο έλεγχος ουσιαστικού περιεχομένου (validation_safety.thin_analysis_content)
απαιτεί πραγματικό ερμηνευτικό κείμενο σε κάθε Οίκο. Οι παλιότερες δοκιμές των
κανόνων δεδομένων (όψεις, κυβερνήτες, ζώδια...) χτίζουν σκόπιμα σκελετικά κείμενα,
οπότε γι' αυτές απενεργοποιείται. Οι δοκιμές με marker «substance» τον κρατούν
ενεργό.
"""

import pytest

import validation_safety


def pytest_configure(config):
    config.addinivalue_line("markers", "substance: ο έλεγχος ουσίας μένει ενεργός")


# Απενεργοποίηση για όλη τη συνεδρία δοκιμών (και για fixtures με scope=module).
validation_safety.SUBSTANCE_CHECK_ENABLED = False


@pytest.fixture(autouse=True)
def _substance_check(request, monkeypatch):
    if request.node.get_closest_marker("substance") is not None:
        monkeypatch.setattr(validation_safety, "SUBSTANCE_CHECK_ENABLED", True)
    yield
