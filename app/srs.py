import time

DAY_MS = 24 * 60 * 60 * 1000
CARD_TYPES = ["audio_type", "zh_to_en", "pronounce", "en_to_zh"]


def now_ms() -> int:
    return int(time.time() * 1000)


def grade(ease: float, interval_days: float, reps: int, grade_label: str):
    """Returns (new_ease, new_interval_days, new_reps, new_due_at_ms)."""
    if grade_label == "again":
        new_ease = max(1.3, ease - 0.2)
        return new_ease, 10 / (24 * 60), 0, now_ms() + 10 * 60 * 1000

    reps += 1
    if grade_label == "hard":
        ease = max(1.3, ease - 0.15)
    elif grade_label == "easy":
        ease = ease + 0.15

    if reps == 1:
        interval_days = 1
    elif reps == 2:
        interval_days = 6
    else:
        interval_days = round(interval_days * ease) or 1

    due_at = now_ms() + int(interval_days * DAY_MS)
    return ease, interval_days, reps, due_at
