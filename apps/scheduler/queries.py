"""
Cross-app data collection for the scheduler module.

This is the ONLY file in apps/scheduler/ that imports from other Django apps
(besides plans, which is a direct model dependency).
"""

import datetime
from collections import defaultdict

from django.db.models import Sum

from apps.difficulty.predict import predict as predict_difficulty
from apps.fatigue.banister import TSSInput, compute
from apps.integrations.models import Activity
from apps.plans.models import UserProgressionScores

from .models import ScheduledWorkout


def get_user_scores(user) -> dict[str, float]:
    """Return {category: score} for the user's progression scores."""
    scores_obj, _ = UserProgressionScores.objects.get_or_create(user=user)
    return scores_obj.as_dict()


def compute_tsb_for_range(user, start_str, end_str) -> dict:
    """Compute TSB for each day in a date range. Returns {date: tsb}."""
    try:
        start_date = datetime.date.fromisoformat(start_str[:10]) if start_str else None
        end_date = datetime.date.fromisoformat(end_str[:10]) if end_str else None
    except (ValueError, TypeError):
        return {}

    if not start_date or not end_date:
        return {}

    warmup_days = 60
    data_start = start_date - datetime.timedelta(days=warmup_days)

    actual_qs = (
        Activity.objects.filter(
            user=user,
            start_datetime__date__gte=data_start,
            start_datetime__date__lte=end_date,
            tss__isnull=False,
        )
        .values("start_datetime__date")
        .annotate(day_tss=Sum("tss"))
    )

    inputs = [
        TSSInput(date=row["start_datetime__date"], tss=row["day_tss"], source="actual")
        for row in actual_qs
    ]

    # Include planned TSS from scheduled workouts
    planned_qs = ScheduledWorkout.objects.filter(
        user=user,
        date__gte=data_start,
        date__lte=end_date,
        completed=False,
    ).select_related("workout")
    actual_dates = {inp.date for inp in inputs}
    planned_by_day: dict[datetime.date, float] = defaultdict(float)
    for sw in planned_qs:
        if sw.date not in actual_dates:
            planned_by_day[sw.date] += sw.workout.tss_estimate
    for dt, tss in planned_by_day.items():
        inputs.append(TSSInput(date=dt, tss=tss, source="planned"))

    if not inputs:
        return {}

    metrics = compute(inputs)
    return {m.date: m.tsb for m in metrics if m.date >= start_date}


def predict_workout_difficulty(workout, user_scores, tsb):
    """Predict difficulty for a workout given user scores and TSB."""
    user_score = user_scores.get(workout.category, 5.0)
    return predict_difficulty(
        workout_score=workout.progression_score,
        user_score=user_score,
        tsb=tsb,
        intended_effort=workout.intended_effort,
    )
