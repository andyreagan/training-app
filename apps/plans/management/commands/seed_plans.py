"""
management command: seed_plans

Creates a WorkoutBlock for every rung in every zone's progression ladder,
then creates Jem Arnold's "Sustainable Training" plan with a representative
weekly schedule.

Run with:
    python manage.py seed_plans
    python manage.py seed_plans --reset   # drops existing data first
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.plans.models import (
    DAY_CHOICES,
    PlanBlock,
    TrainingPlan,
    WorkoutBlock,
    WorkoutCategory,
)
from apps.plans.progressions import LADDERS, all_rungs, human_summary


CATEGORY_DESCRIPTIONS = {
    "recovery":   "Easy active recovery. Stay below 55% FTP the whole ride. "
                  "Purpose: flush fatigue, not accumulate fitness.",
    "endurance":  "Zone 2 aerobic base. Fully conversational pace. "
                  "The primary currency of Jem's Sustainable Training framework.",
    "tempo":      "Comfortably uncomfortable sustained effort. "
                  "Builds aerobic capacity above pure Z2 without heavy recovery cost.",
    "sweet_spot": "88–93% FTP — Jem's highest-value training zone. "
                  "High aerobic stimulus, manageable fatigue. Progress by lengthening "
                  "individual intervals, not just adding reps.",
    "threshold":  "95–105% FTP. Hard sustained efforts that improve your FTP ceiling. "
                  "Even a 1-minute increase in interval duration is meaningful here.",
    "vo2max":     "106–120% FTP. Short, hard intervals targeting VO2max. "
                  "Progression: 4×4 min → 4×5 min → 3×6 min → 4×6 min → 3×8 min …\n"
                  "Longer single efforts are harder even when total volume drops.",
    "anaerobic":  "Above 120% FTP. Short maximal efforts. "
                  "Rest is generous — goal is max power output, not grinding.",
}

# ── Plan template ──────────────────────────────────────────────────────────────
#
# "Sustainable Training" by Jem Arnold (sparecycles.blog/2022/01/02/sustainable-training/)
#
# Weekly rhythm (loosely — adapt to life):
#   Mon: rest
#   Tue: quality (sweet spot / threshold / vo2max depending on phase)
#   Wed: endurance Z2
#   Thu: quality
#   Fri: rest or recovery
#   Sat: long endurance
#   Sun: endurance or sweet spot
#
# Four 4-week phases: Foundation → Base → Build → Peak
# Each phase uses scores appropriate for a mid-level athlete (score ≈ 3–7).
# Athletes adjust by using their own scores to pick the actual rung.

# (week, day_of_week, category, target_score)
PLAN_WEEKS = []

# Phase 1 — Foundation (weeks 1–4): establish aerobic base, intro quality
for wk in range(1, 5):
    PLAN_WEEKS += [
        (wk, 1, "endurance",  3.0),   # Tue — moderate Z2
        (wk, 2, "endurance",  2.0),   # Wed — easy Z2
        (wk, 3, "sweet_spot", 2.0),   # Thu — intro SS
        (wk, 5, "endurance",  4.0),   # Sat — longer Z2
        (wk, 6, "recovery",   2.5),   # Sun — recovery spin
    ]

# Phase 2 — Base (weeks 5–10): build SS volume, add tempo
for wk in range(5, 11):
    PLAN_WEEKS += [
        (wk, 1, "sweet_spot", 3.5),   # Tue — SS main set
        (wk, 2, "endurance",  4.0),   # Wed — Z2
        (wk, 3, "tempo",      3.0),   # Thu — tempo
        (wk, 5, "endurance",  6.0),   # Sat — long Z2
        (wk, 6, "sweet_spot", 2.0),   # Sun — easy SS or Z2
    ]

# Phase 3 — Build (weeks 11–16): introduce threshold, push SS
for wk in range(11, 17):
    PLAN_WEEKS += [
        (wk, 1, "sweet_spot", 5.0),   # Tue — classic 2×20 territory
        (wk, 2, "endurance",  5.0),   # Wed
        (wk, 3, "threshold",  3.0),   # Thu — threshold work
        (wk, 5, "endurance",  7.0),   # Sat — long ride
        (wk, 6, "sweet_spot", 4.0),   # Sun
    ]

# Phase 4 — Peak (weeks 17–20): vo2max, maintain base
for wk in range(17, 21):
    PLAN_WEEKS += [
        (wk, 1, "vo2max",     4.0),   # Tue — VO2max (e.g. 3×6 min)
        (wk, 2, "endurance",  5.0),   # Wed
        (wk, 3, "threshold",  5.0),   # Thu
        (wk, 5, "endurance",  8.0),   # Sat — long Z2
        (wk, 6, "sweet_spot", 5.0),   # Sun
    ]


class Command(BaseCommand):
    help = "Seed workout blocks and the Sustainable Training plan."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing WorkoutBlocks and plans before seeding.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            WorkoutBlock.objects.all().delete()
            TrainingPlan.objects.filter(
                slug="sustainable-training"
            ).delete()
            self.stdout.write("Existing data cleared.")

        # ── 1. Create WorkoutBlocks ────────────────────────────────────────────
        self.stdout.write("Creating workout blocks…")
        blocks_by_key: dict[tuple, WorkoutBlock] = {}

        for category in WorkoutCategory.values:
            cat_desc = CATEGORY_DESCRIPTIONS.get(category, "")
            for step, rung in all_rungs(category):
                summary = rung.summary()
                cat_label = WorkoutCategory(category).label
                name = f"{cat_label} — {summary}"
                slug_base = slugify(f"{category} {rung.score}")
                slug = slug_base
                # Ensure uniqueness in case of rounding collisions
                n = 1
                while WorkoutBlock.objects.filter(slug=slug).exclude(
                    category=category, progression_score=rung.score
                ).exists():
                    slug = f"{slug_base}-{n}"
                    n += 1

                description = rung.note or cat_desc
                block, created = WorkoutBlock.objects.update_or_create(
                    category=category,
                    progression_score=rung.score,
                    defaults={
                        "name": name,
                        "slug": slug,
                        "description": description,
                        "source_url": "https://sparecycles.blog/2022/01/02/sustainable-training/",
                    },
                )
                blocks_by_key[(category, rung.score)] = block
                verb = "Created" if created else "Updated"
                self.stdout.write(f"  {verb}: {block}")

        # ── 2. Create the Sustainable Training plan ────────────────────────────
        self.stdout.write("\nCreating Sustainable Training plan…")
        plan, _ = TrainingPlan.objects.update_or_create(
            slug="sustainable-training",
            defaults={
                "name": "Sustainable Training",
                "description": (
                    "A 20-week aerobic-first training plan by Jem Arnold "
                    "(sparecycles.blog). Heavy Zone 2 base, sweet spot as the "
                    "primary quality work, progressive introduction of threshold "
                    "and VO2max. Progression levels automatically adapt the "
                    "interval structure to your current fitness."
                ),
                "duration_weeks": 20,
                "target_hours_per_week_low": 6,
                "target_hours_per_week_high": 12,
                "source_url": "https://sparecycles.blog/2022/01/02/sustainable-training/",
                "is_published": True,
            },
        )

        # Clear old plan blocks
        PlanBlock.objects.filter(plan=plan).delete()

        # Map (category, target_score) → closest WorkoutBlock.
        # Because seed_plans creates every rung before building the plan, an
        # exact match always exists in blocks_by_key.  The fallback handles
        # any hypothetical float precision edge-cases.
        def find_block(category, target_score):
            if (category, target_score) in blocks_by_key:
                return blocks_by_key[(category, target_score)]
            # Closest by absolute score difference
            candidates = [
                (abs(k[1] - target_score), v)
                for k, v in blocks_by_key.items()
                if k[0] == category
            ]
            if candidates:
                return min(candidates, key=lambda x: x[0])[1]
            return None

        created_blocks = 0
        for wk, dow, category, target_score in PLAN_WEEKS:
            block = find_block(category, target_score)
            if not block:
                self.stdout.write(
                    self.style.WARNING(f"  No block found for {category} @ {target_score}")
                )
                continue
            PlanBlock.objects.create(
                plan=plan,
                workout=block,
                week_number=wk,
                day_of_week=dow,
                order=0,
            )
            created_blocks += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {WorkoutBlock.objects.count()} workout blocks, "
                f"{created_blocks} plan blocks in '{plan.name}'."
            )
        )
