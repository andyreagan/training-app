from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class DataSource(models.TextChoices):
    STRAVA = "strava", "Strava"
    GARMIN = "garmin", "Garmin"
    MANUAL = "manual", "Manual"


class EffortSource(models.TextChoices):
    STRAVA = "strava", "Strava"
    MANUAL = "manual", "Manual"
    HR_ESTIMATE = "hr_estimate", "HR estimate"


class Activity(models.Model):
    """
    A completed training activity from any data source.

    All source-specific raw data is stored in ``raw_data`` so we
    can add new sources without schema changes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities"
    )
    source = models.CharField(max_length=20, choices=DataSource.choices)
    external_id = models.CharField(max_length=200, help_text="ID in the source system")

    name = models.CharField(max_length=300)
    sport_type = models.CharField(max_length=50)
    start_datetime = models.DateTimeField()

    duration_seconds = models.PositiveIntegerField()
    distance_meters = models.FloatField(null=True, blank=True)
    elevation_gain_meters = models.FloatField(null=True, blank=True)

    # Power metrics
    average_watts = models.FloatField(null=True, blank=True)
    normalized_power = models.FloatField(null=True, blank=True)
    intensity_factor = models.FloatField(null=True, blank=True)
    tss = models.FloatField(null=True, blank=True, help_text="Training Stress Score")

    # HR metrics
    average_hr = models.PositiveIntegerField(null=True, blank=True)
    max_hr = models.PositiveIntegerField(null=True, blank=True)

    # Perceived effort (RPE) — 1 = trivial, 10 = maximum
    perceived_effort = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Subjective effort rating 1–10",
    )
    effort_source = models.CharField(
        max_length=20,
        choices=EffortSource.choices,
        blank=True,
        default="",
        help_text="Where the effort rating came from",
    )

    # Second-by-second streams (fetched from Strava streams API)
    power_data = models.JSONField(
        null=True,
        blank=True,
        help_text='{"time": [0, 1, ...], "watts": [150, 153, ...]}',
    )
    hr_data = models.JSONField(
        null=True,
        blank=True,
        help_text='{"time": [0, 1, ...], "heartrate": [120, 122, ...]}',
    )

    # HR-based TSS — used when power-based TSS is unavailable
    hr_tss = models.FloatField(
        null=True,
        blank=True,
        help_text="HR-based Training Stress Score (fallback when no power)",
    )

    # Strava-specific extras cached here for convenience
    strava_kudos = models.PositiveIntegerField(null=True, blank=True)
    strava_url = models.URLField(blank=True)

    raw_data = models.JSONField(default=dict, help_text="Full response from source API")

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["source", "external_id"]]
        ordering = ["-start_datetime"]

    def __str__(self):
        return f"{self.name} ({self.source} — {self.start_datetime.date()})"

    @property
    def has_power_stream(self) -> bool:
        return bool(self.power_data and self.power_data.get("watts"))

    @property
    def has_hr_stream(self) -> bool:
        return bool(self.hr_data and self.hr_data.get("heartrate"))

    @property
    def effective_tss(self) -> float | None:
        """Power-based TSS if available, otherwise HR-based TSS."""
        return self.tss if self.tss is not None else self.hr_tss

    @property
    def effort_label(self) -> str:
        if self.perceived_effort is None:
            return ""
        labels = {
            1: "Very easy",
            2: "Easy",
            3: "Light",
            4: "Moderate",
            5: "Somewhat hard",
            6: "Hard",
            7: "Very hard",
            8: "Extremely hard",
            9: "Near maximal",
            10: "Maximal",
        }
        return labels.get(self.perceived_effort, "")

    @property
    def duration_formatted(self):
        h, rem = divmod(self.duration_seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m"
        return f"{m}m {s:02d}s"

    @property
    def distance_km(self):
        if self.distance_meters:
            return round(self.distance_meters / 1000, 1)
        return None
