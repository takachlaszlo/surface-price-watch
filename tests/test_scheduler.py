from datetime import datetime

from pricewatch.scheduler import next_target


def test_next_target_today_or_tomorrow():
    assert next_target(datetime(2026, 9, 30, 6, 59), "07:00") == datetime(2026, 9, 30, 7, 0)
    assert next_target(datetime(2026, 9, 30, 7, 0), "07:00") == datetime(2026, 10, 1, 7, 0)
    assert next_target(datetime(2026, 9, 30, 23, 30), "07:30") == datetime(2026, 10, 1, 7, 30)
