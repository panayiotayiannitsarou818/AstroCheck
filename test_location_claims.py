from models import Chart, Point
import validator as V

HOUSES = {"Ήλιος": 3, "Σελήνη": 10, "Άρης": 10, "Δίας": 11, "Βόρειος Δεσμός": 8}


def _chart():
    return Chart(points=[
        Point("x", n, "", 0, 0, 0, 0.0, h, False, "node" if "Δεσμ" in n else "planet")
        for n, h in HOUSES.items()
    ])


def test_relative_clause_belongs_to_nearest_point():
    text = ("Ο Βόρειος Δεσμός στον Καρκίνο κυβερνάται από τη Σελήνη, η οποία "
            "βρίσκεται στην Παρθένο 25°58′02″, στον 10ο Οίκο.")
    assert V._location_claim_errors(_chart(), text) == []


def test_real_wrong_claim_is_still_caught():
    text = "Ο Βόρειος Δεσμός βρίσκεται στον 10ο Οίκο."
    errors = V._location_claim_errors(_chart(), text)
    assert [(e[0], e[1], e[2]) for e in errors] == [("Βόρειος Δεσμός", 10, 8)]


def test_wrong_claim_of_second_point_is_still_caught():
    text = "Ο Δίας συνδέεται με τη Σελήνη, η οποία βρίσκεται στον 4ο Οίκο."
    errors = V._location_claim_errors(_chart(), text)
    assert [(e[0], e[1], e[2]) for e in errors] == [("Σελήνη", 4, 10)]


def test_correct_claim_passes():
    assert V._location_claim_errors(_chart(), "Ο Άρης βρίσκεται στον 10ο Οίκο.") == []
