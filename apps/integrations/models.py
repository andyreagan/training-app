from django.conf import settings
from django.db import models


class DataSource(models.TextChoices):
    STRAVA = "strava", "Strava"
    GARMIN = "garmin", "Garmin"
    MANUAL = "manual", "Manual"


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
