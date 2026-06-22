"""
Cross-app data collection for the fatigue module.

This is the ONLY file in apps/fatigue/ that imports from other Django apps.
The views and pure engines (banister.py, power.py, hr.py) do not.
"""

import datetime
from collections import defaultdict

from django.db.models import F, Sum
from django.db.models.functions import Coalesce

from apps.integrations.models import Activity
from apps.scheduler.models import ScheduledWorkout

from .banister import TSSInput, compute
from .power import ActivityCurveInput, compute_power_curve


def collect_daily_tss(user, start_date, end_date):
    """
    Merge actual TSS from completed activities and estimated TSS from
    scheduled workouts into a unified list of TSSInput.

    Uses power-based TSS when available, falls back to HR-based TSS.
    """
    today = datetime.date.today()
    inputs: list[TSSInput] = []

    # Actual TSS from activities (COALESCE power TSS with HR TSS)
    actual_qs = (
        Activity.objects.filter(
            user=user,
            start_datetime__date__gte=start_date,
            start_datetime__date__lte=min(end_date, today),
        )
        .exclude(tss__isnull=True, hr_tss__isnull=True)
        .annotate(effective_tss=Coalesce(F("tss"), F("hr_tss")))
        .values("start_datetime__date")
        .annotate(day_tss=Sum("effective_tss"))
        .order_by("start_datetime__date")
    )
    actual_dates = set()
    for row in actual_qs:
        dt = row["start_datetime__date"]
        inputs.append(TSSInput(date=dt, tss=row["day_tss"], source="actual"))
        actual_dates.add(dt)

    # Planned TSS from scheduled workouts
    planned_qs = ScheduledWorkout.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date,
        completed=False,
    ).select_related("workout")

    planned_by_day: dict[datetime.date, float] = defaultdict(float)
    for sw in planned_qs:
        if sw.date not in actual_dates:
            planned_by_day[sw.date] += sw.workout.tss_estimate

    for dt, tss in planned_by_day.items():
        inputs.append(TSSInput(date=dt, tss=tss, source="planned"))

    return inputs


def tsb_for_date(user, target_date):
    """Compute TSB on a specific date using activity history."""
    warmup_days = 60
    start = target_date - datetime.timedelta(days=warmup_days + 42)

    actual_qs = (
        Activity.objects.filter(
            user=user,
            start_datetime__date__gte=start,
            start_datetime__date__lte=target_date,
        )
        .exclude(tss__isnull=True, hr_tss__isnull=True)
        .annotate(effective_tss=Coalesce(F("tss"), F("hr_tss")))
        .values("start_datetime__date")
        .annotate(day_tss=Sum("effective_tss"))
    )

    inputs = [
        TSSInput(date=row["start_datetime__date"], tss=row["day_tss"], source="actual")
        for row in actual_qs
    ]

    if not inputs:
        return 0.0

    metrics = compute(inputs)
    for m in reversed(metrics):
        if m.date <= target_date:
            return m.tsb
    return 0.0


def collect_activity_curves(user, start_date, end_date):
    """
    Build ActivityCurveInput list from activities with power data in a range.
    """
    activities = Activity.objects.filter(
        user=user,
        start_datetime__date__gte=start_date,
        start_datetime__date__lte=end_date,
        power_data__isnull=False,
    ).order_by("start_datetime")

    result: list[ActivityCurveInput] = []
    for act in activities:
        watts = act.power_data.get("watts", [])
        if not watts:
            continue
        curve = compute_power_curve(watts)
        if not curve:
            continue
        tsb = tsb_for_date(user, act.start_datetime.date())
        result.append(
            ActivityCurveInput(
                date=act.start_datetime.date(),
                activity_name=act.name,
                curve=curve,
                perceived_effort=act.perceived_effort,
                tsb=tsb,
            )
        )
    return result
