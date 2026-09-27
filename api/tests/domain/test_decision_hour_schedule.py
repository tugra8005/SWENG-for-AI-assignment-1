from datetime import UTC, datetime, timedelta

from mesveret.domain.decision_hour import next_occurrence
from mesveret.domain.regulation import Regulation

SPEC = Regulation.defaults().decision_hour()


def test_next_sunday_20_istanbul_from_tuesday():
    tuesday = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)  # Salı 10:00 İstanbul
    assert next_occurrence(tuesday, SPEC) == datetime(2026, 10, 4, 17, 0, tzinfo=UTC)


def test_occurrence_is_strictly_after_the_given_moment():
    sunday_20 = datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
    assert next_occurrence(sunday_20, SPEC) == sunday_20 + timedelta(days=7)
    assert next_occurrence(sunday_20 - timedelta(seconds=1), SPEC) == sunday_20


def test_later_on_sunday_rolls_to_next_week():
    sunday_21 = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
    assert next_occurrence(sunday_21, SPEC) == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)


def test_schedule_is_read_from_regulation():
    reg = Regulation({**Regulation.defaults().values, "karar_saati": {
        "gun": "CARSAMBA", "saat": "12:30", "tz": "Europe/Istanbul", "pencere_dakika": 30,
    }})
    spec = reg.decision_hour()
    tuesday = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)
    assert next_occurrence(tuesday, spec) == datetime(2026, 9, 30, 9, 30, tzinfo=UTC)
