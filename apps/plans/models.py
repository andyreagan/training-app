from django.db import models
from django.conf import settings
from django.utils.text import slugify

from .progressions import (
    LADDERS,
    ZONE_POWER,
    compute_structure,
    compute_total_duration_minutes,
    compute_tss_estimate,
    human_summary,
    rung_for_score,
    score_label,
    all_rungs,
)


class WorkoutCategory(models.TextChoices):
    RECOVERY   = "recovery",   "Recovery"
    ENDURANCE  = "endurance",  "Endurance"
    TEMPO      = "tempo",      "Tempo"
    SWEET_SPOT = "sweet_spot", "Sweet Spot"
    THRESHOLD  = "threshold",  "Threshold"
    VO2MAX     = "vo2max",     "VO2 Max"
    ANAEROBIC  = "anaerobic",  "Anaerobic"


CATEGORY_COLORS = {
    WorkoutCategory.RECOVERY:   "#94a3b8",
    WorkoutCategory.ENDURANCE:  "#4ade80",
    WorkoutCategory.TEMPO:      "#facc15",
    WorkoutCategory.SWEET_SPOT: "#fb923c",
    WorkoutCategory.THRESHOLD:  "#f87171",
    WorkoutCategory.VO2MAX:     "#c084fc",
    WorkoutCategory.ANAEROBIC:  "#e879f9",
}


class WorkoutBlock(models.Model):
    """
    A specific rung on a zone's progression ladder.

    The interval structure is fully determined by (category, progression_score)
    via progressions.py — the score maps to the highest rung whose threshold
    is ≤ the score.  Absolute power targets are calculated at download/display
    time by applying the athlete's FTP.

    total_duration_minutes and tss_estimate are cached on save so they can
    be used in DB queries (ordering, filtering) without re-computing every time.
    """

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    category = models.CharField(max_length=20, choices=WorkoutCategory.choices, db_index=True)

    # The score threshold at which this rung is unlocked (1.0–10.0).
    # This IS the rung — it uniquely identifies a step on the ladder.
    progression_score = models.FloatField(
        help_text="Score threshold (1.0–10.0) at which this rung unlocks. "
                  "Maps directly to a Rung in progressions.LADDERS."
    )

    # Cached computed fields — updated automatically on save.
    total_duration_minutes = models.PositiveIntegerField(editable=False, default=0)
    tss_estimate = models.PositiveIntegerField(editable=False, default=0)

    # Optional human-readable override (e.g. "Classic 2×20").
    # If blank, auto-generated from the progression ladder.
    description = models.TextField(blank=True)
    source_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "progression_score"]
        unique_together = [["category", "progression_score"]]

    def __str__(self):
        return f"{self.name} (score {self.progression_score})"

    # ── Computed properties ────────────────────────────────────────────────────

    @property
    def structure(self) -> list[dict]:
        """Live interval structure from the progression ladder."""
        return compute_structure(self.category, self.progression_score)

    @property
    def rung(self):
        """The Rung object this block maps to."""
        _, r = rung_for_score(self.category, self.progression_score)
        return r

    @property
    def color(self) -> str:
        return CATEGORY_COLORS.get(self.category, "#6b7280")

    @property
    def category_label(self) -> str:
        return WorkoutCategory(self.category).label if self.category else ""

    @property
    def summary(self) -> str:
        return human_summary(self.category, self.progression_score)

    @property
    def score_label(self) -> str:
        return score_label(self.progression_score)

    @property
    def zone_power(self) -> tuple[int, int]:
        return ZONE_POWER.get(self.category, (56, 75))

    def structure_with_watts(self, ftp: int) -> list[dict]:
        """Return structure steps with absolute watt targets applied."""
        steps = []
        for step in self.structure:
            s = dict(step)
            s["watts_low"]  = round(ftp * step["power_low"]  / 100)
            s["watts_high"] = round(ftp * step["power_high"] / 100)
            if "rest_power_low" in step:
                s["rest_watts_low"]  = round(ftp * step["rest_power_low"]  / 100)
                s["rest_watts_high"] = round(ftp * step["rest_power_high"] / 100)
            steps.append(s)
        return steps

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        # Auto-generate slug if not set
        if not self.slug:
            self.slug = slugify(self.name)
        # Cache computed fields
        self.total_duration_minutes = compute_total_duration_minutes(
            self.category, self.progression_score
        )
        self.tss_estimate = compute_tss_estimate(self.category, self.progression_score)
        super().save(*args, **kwargs)


# ── Training plan ──────────────────────────────────────────────────────────────

class TrainingPlan(models.Model):
    """
    A multi-week training plan composed of WorkoutBlock prescriptions.
    The plan prescribes *zones* (and optionally target scores); the athlete's
    actual per-zone scores determine the specific interval structure they see.
    """

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    duration_weeks = models.PositiveIntegerField()
    target_hours_per_week_low  = models.DecimalField(max_digits=4, decimal_places=1)
    target_hours_per_week_high = models.DecimalField(max_digits=4, decimal_places=1)
    source_url = models.URLField(blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def weekly_structure(self):
        from collections import defaultdict
        grouped = defaultdict(lambda: defaultdict(list))
        for pb in self.planblock_set.select_related("workout").order_by(
            "week_number", "day_of_week", "order"
        ):
            grouped[pb.week_number][pb.day_of_week].append(pb)
        return {w: dict(days) for w, days in sorted(grouped.items())}


DAY_CHOICES = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
    (4, "Friday"),  (5, "Saturday"), (6, "Sunday"),
]


class PlanBlock(models.Model):
    """
    Places a WorkoutBlock on a specific week + day within a TrainingPlan.
    The workout's progression_score is the *minimum recommended score* for
    this slot — athletes well above it may wish to target a higher rung.
    """

    plan       = models.ForeignKey(TrainingPlan, on_delete=models.CASCADE)
    workout    = models.ForeignKey(WorkoutBlock, on_delete=models.CASCADE)
    week_number  = models.PositiveIntegerField()
    day_of_week  = models.IntegerField(choices=DAY_CHOICES)
    order        = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["week_number", "day_of_week", "order"]

    def __str__(self):
        return (
            f"{self.plan} — Wk {self.week_number} "
            f"{self.get_day_of_week_display()}: {self.workout}"
        )


class UserPlan(models.Model):
    """Links a user to a training plan with a chosen start date."""

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_plans")
    plan       = models.ForeignKey(TrainingPlan, on_delete=models.CASCADE)
    start_date = models.DateField()
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.plan} (from {self.start_date})"

    def deactivate_others(self):
        UserPlan.objects.filter(user=self.user, is_active=True).exclude(pk=self.pk).update(
            is_active=False
        )


# ── Per-user progression scores ────────────────────────────────────────────────

class UserProgressionScores(models.Model):
    """
    Stores a continuous progression score (1.0–10.0) per zone for each athlete.

    The score drives rung selection: the athlete always does the highest rung
    whose threshold is ≤ their current score.  Scores advance as workouts are
    completed; they can also be set manually (e.g. when first starting, or after
    a fitness test).

    Default 5.0 ≈ the "plain FTP" midpoint — a reasonable starting assumption
    before any training history exists.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="progression_scores",
    )

    recovery_score   = models.FloatField(default=5.0)
    endurance_score  = models.FloatField(default=5.0)
    tempo_score      = models.FloatField(default=5.0)
    sweet_spot_score = models.FloatField(default=5.0)
    threshold_score  = models.FloatField(default=5.0)
    vo2max_score     = models.FloatField(default=5.0)
    anaerobic_score  = models.FloatField(default=5.0)

    updated_at = models.DateTimeField(auto_now=True)

    SCORE_FIELDS = {
        "recovery":   "recovery_score",
        "endurance":  "endurance_score",
        "tempo":      "tempo_score",
        "sweet_spot": "sweet_spot_score",
        "threshold":  "threshold_score",
        "vo2max":     "vo2max_score",
        "anaerobic":  "anaerobic_score",
    }

    def score_for(self, category: str) -> float:
        field = self.SCORE_FIELDS.get(category)
        return getattr(self, field, 5.0) if field else 5.0

    def set_score(self, category: str, value: float):
        field = self.SCORE_FIELDS.get(category)
        if field:
            setattr(self, field, max(1.0, min(10.0, value)))

    def as_dict(self) -> dict[str, float]:
        return {cat: self.score_for(cat) for cat in self.SCORE_FIELDS}

    def rung_summary(self) -> dict[str, dict]:
        """Return current rung info for every zone — useful for profile/dashboard."""
        from .progressions import rung_for_score, next_rung, ladder_length

        ZONE_LABELS = {
            "recovery":   "Recovery",
            "endurance":  "Endurance",
            "tempo":      "Tempo",
            "sweet_spot": "Sweet Spot",
            "threshold":  "Threshold",
            "vo2max":     "VO2 Max",
            "anaerobic":  "Anaerobic",
        }

        out = {}
        for cat, field in self.SCORE_FIELDS.items():
            score = getattr(self, field)
            step, rung = rung_for_score(cat, score)
            next_info = next_rung(cat, score)
            out[cat] = {
                "zone_label":   ZONE_LABELS[cat],
                "score":        score,
                "score_label":  score_label(score),
                "step":         step,
                "total_steps":  ladder_length(cat),
                "summary":      rung.summary(),
                "note":         rung.note,
                "next_summary": next_info[1].summary() if next_info else None,
                "next_score":   next_info[1].score if next_info else None,
            }
        return out

    def __str__(self):
        return f"Progression scores for {self.user}"
