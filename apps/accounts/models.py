from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user with cycling profile data."""

    ftp = models.PositiveIntegerField(
        null=True, blank=True, help_text="Functional Threshold Power in watts"
    )
    max_hr = models.PositiveIntegerField(
        null=True, blank=True, help_text="Maximum heart rate in bpm"
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, help_text="Body weight in kg"
    )

    # Strava OAuth tokens — encrypted in prod via env-controlled secret key
    strava_athlete_id = models.BigIntegerField(null=True, blank=True, unique=True)
    strava_access_token = models.TextField(null=True, blank=True)
    strava_refresh_token = models.TextField(null=True, blank=True)
    strava_token_expires_at = models.DateTimeField(null=True, blank=True)

    @property
    def watts_per_kg(self):
        if self.ftp and self.weight_kg:
            return round(float(self.ftp) / float(self.weight_kg), 2)
        return None

    @property
    def strava_connected(self):
        return bool(self.strava_athlete_id and self.strava_refresh_token)

    def __str__(self):
        return self.username
