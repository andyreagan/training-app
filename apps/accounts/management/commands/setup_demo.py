"""
management command: setup_demo

Creates (or resets) the demo user and seeds realistic training data.
Safe to run repeatedly — it wipes the demo user's data first, then rebuilds.

Intended to run on a cron, e.g. every hour:
    python manage.py setup_demo

Environment variables:
    DEMO_USERNAME  (default: "demo")
    DEMO_PASSWORD  (default: "demo1234")
"""

import datetime
import os
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo1234")
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@example.com")


class Command(BaseCommand):
    help = "Create or reset the demo user with seeded training data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress output (useful when called from cron).",
        )

    def handle(self, *args, **options):
        quiet = options["quiet"]

        def log(msg):
            if not quiet:
                self.stdout.write(msg)

        # ── 1. Get or create the demo user ─────────────────────────────────────
        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={
                "email": DEMO_EMAIL,
                "first_name": "Demo",
                "last_name": "Rider",
                "max_hr": 185,
                "resting_hr": 52,
                "is_active": True,
            },
        )
        user.set_password(DEMO_PASSWORD)
        if not created:
            # Ensure profile fields stay current even after a reset
            user.first_name = "Demo"
            user.last_name = "Rider"
            user.max_hr = 185
            user.resting_hr = 52
        user.save()
        log(f"{'Created' if created else 'Reset'} demo user: {DEMO_USERNAME}")

        # ── 2. Wipe all demo-owned data ────────────────────────────────────────
        from apps.accounts.models import FTPHistory, WeightHistory
        from apps.integrations.models import Activity
        from apps.plans.models import UserPlan, UserProgressionScores
        from apps.scheduler.models import ScheduledWorkout

        FTPHistory.objects.filter(user=user).delete()
        WeightHistory.objects.filter(user=user).delete()
        Activity.objects.filter(user=user).delete()
        ScheduledWorkout.objects.filter(user=user).delete()
        UserPlan.objects.filter(user=user).delete()

        log("Cleared existing demo data.")

        # ── 3. FTP history ─────────────────────────────────────────────────────
        today = datetime.date.today()
        # Three FTP entries spanning ~18 months of realistic improvement
        ftp_entries = [
            (today - datetime.timedelta(days=540), 218, "ramp_test"),
            (today - datetime.timedelta(days=270), 237, "20min_test"),
            (today - datetime.timedelta(days=60), 251, "ramp_test"),
        ]
        for date, ftp, source in ftp_entries:
            user.record_ftp(ftp, effective_date=date, source=source)
        log(f"Seeded {len(ftp_entries)} FTP history entries (current FTP: 251W).")

        # ── 4. Weight history ──────────────────────────────────────────────────
        weight_entries = [
            (today - datetime.timedelta(days=540), 76.2),
            (today - datetime.timedelta(days=270), 74.8),
            (today - datetime.timedelta(days=60), 73.5),
            (today - datetime.timedelta(days=7), 73.1),
        ]
        for date, weight in weight_entries:
            user.record_weight(weight, effective_date=date)
        log(f"Seeded {len(weight_entries)} weight history entries.")

        # ── 5. Activities (past 90 days) ───────────────────────────────────────
        _seed_activities(user, today, log)

        # ── 6. Progression scores ──────────────────────────────────────────────
        scores, _ = UserProgressionScores.objects.get_or_create(user=user)
        scores.set_score("endurance", 6.5)
        scores.set_score("sweetspot", 5.0)
        scores.set_score("threshold", 4.0)
        scores.set_score("vo2max", 3.5)
        scores.set_score("anaerobic", 3.0)
        scores.save()
        log("Seeded progression scores.")

        # ── 7. Upcoming scheduled workouts (next 4 weeks) ─────────────────────
        _seed_scheduled_workouts(user, today, log)

        log(self.style.SUCCESS("Demo data seeded successfully."))


# ── Seeding helpers ────────────────────────────────────────────────────────────


def _seed_activities(user, today, log):
    """Create ~45 realistic activities over the past 90 days."""
    from apps.integrations.models import Activity, DataSource

    rng = random.Random(42)  # deterministic

    # Each tuple: (days_ago, type, name, duration_min, avg_watts, avg_hr, effort)
    # We'll space them out with a realistic 3-on-1-off pattern.
    templates = [
        ("endurance_ride", "Endurance", 90, 175, 142, 5),
        ("endurance_ride", "Long Ride", 150, 168, 138, 6),
        ("sweetspot", "Sweet Spot Intervals", 70, 215, 161, 7),
        ("threshold", "Threshold Blocks", 60, 238, 170, 8),
        ("vo2max", "VO2 Max Efforts", 50, 265, 178, 9),
        ("recovery_ride", "Recovery Spin", 45, 140, 120, 3),
        ("race_day", "Group Ride", 120, 195, 158, 8),
    ]

    ftp = 251
    activities_created = 0
    days_ago = 1

    while days_ago <= 90:
        # Pick a template weighted toward endurance
        tpl = rng.choices(templates, weights=[4, 2, 3, 2, 1, 3, 1], k=1)[0]
        category, name_base, dur_min, base_watts, base_hr, effort = tpl

        # Small jitter so every ride looks slightly different
        dur_seconds = int(dur_min * 60 * rng.uniform(0.9, 1.1))
        avg_watts = int(base_watts * rng.uniform(0.95, 1.05))
        np_watts = int(avg_watts * rng.uniform(1.02, 1.08))
        avg_hr = int(base_hr * rng.uniform(0.97, 1.03))

        if_val = round(np_watts / ftp, 3)
        tss = round((dur_seconds * np_watts * if_val) / (ftp * 3600) * 100, 1)

        # Synthetic second-by-second power stream (short representative sample)
        n = min(dur_seconds, 3600)  # cap stream length for storage
        watts_stream = [max(0, avg_watts + rng.randint(-40, 40)) for _ in range(n)]
        hr_stream = [max(60, avg_hr + rng.randint(-8, 8)) for _ in range(n)]

        start_dt = timezone.make_aware(
            datetime.datetime.combine(
                today - datetime.timedelta(days=days_ago),
                datetime.time(rng.randint(6, 10), rng.randint(0, 59)),
            )
        )

        Activity.objects.create(
            user=user,
            external_id=f"demo_{days_ago}_{rng.randint(1000, 9999)}",
            source=DataSource.STRAVA,
            name=f"{name_base} — {(today - datetime.timedelta(days=days_ago)).strftime('%b %d')}",
            sport_type="Ride",
            start_datetime=start_dt,
            duration_seconds=dur_seconds,
            distance_meters=int(dur_seconds * rng.uniform(6.5, 8.5)),
            elevation_gain_meters=int(dur_seconds * rng.uniform(0.05, 0.2)),
            average_watts=avg_watts,
            normalized_power=np_watts,
            average_hr=avg_hr,
            tss=tss,
            intensity_factor=if_val,
            perceived_effort=max(1, min(10, effort + rng.randint(-1, 1))),
            effort_source="manual" if rng.random() > 0.3 else "strava",
            power_data={"time": list(range(n)), "watts": watts_stream},
            hr_data={"time": list(range(n)), "heartrate": hr_stream},
        )

        activities_created += 1
        # Skip 0–2 days between activities (rest days)
        days_ago += rng.randint(1, 3)

    log(f"Seeded {activities_created} activities over the past 90 days.")


def _seed_scheduled_workouts(user, today, log):
    """Schedule ~16 workouts over the next 4 weeks using real WorkoutBlocks."""
    from apps.plans.models import WorkoutBlock
    from apps.scheduler.models import ScheduledWorkout

    rng = random.Random(99)

    # Pull real workouts by category
    def pick(category, n=4):
        qs = list(WorkoutBlock.objects.filter(category=category).order_by("progression_score"))
        if not qs:
            return []
        # Pick n spread across the progression range
        step = max(1, len(qs) // n)
        return qs[::step][:n]

    # Week 1: Mon recovery, Wed SS, Fri threshold, Sat long
    week_pattern = [1, 3, 5, 6]  # Mon=0 baseline from today's Monday

    monday = today - datetime.timedelta(days=today.weekday())  # this week's Monday

    endurance_workouts = pick("endurance", 4)
    ss_workouts = pick("sweetspot", 4)
    threshold_workouts = pick("threshold", 4)

    workout_rotation = (
        [("endurance", w) for w in endurance_workouts]
        + [("sweetspot", w) for w in ss_workouts]
        + [("threshold", w) for w in threshold_workouts]
    )
    rng.shuffle(workout_rotation)

    created = 0
    wi = 0
    for week_offset in range(4):  # 4 weeks
        for day_offset in week_pattern:
            date = monday + datetime.timedelta(weeks=week_offset + 1, days=day_offset)
            if wi >= len(workout_rotation):
                break
            _, workout = workout_rotation[wi]
            wi += 1
            ScheduledWorkout.objects.get_or_create(
                user=user,
                workout=workout,
                date=date,
                defaults={"notes": "Demo schedule"},
            )
            created += 1

    log(f"Seeded {created} scheduled workouts over the next 4 weeks.")
