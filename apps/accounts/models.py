import datetime as _dt

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user with cycling profile data."""

    max_hr = models.PositiveIntegerField(
        null=True, blank=True, help_text="Maximum heart rate in bpm"
    )
    resting_hr = models.PositiveIntegerField(
        null=True, blank=True, help_text="Resting heart rate in bpm"
    )

    # Strava OAuth tokens
    strava_athlete_id = models.BigIntegerField(null=True, blank=True, unique=True)
    strava_access_token = models.TextField(null=True, blank=True)
    strava_refresh_token = models.TextField(null=True, blank=True)
    strava_token_expires_at = models.DateTimeField(null=True, blank=True)

    # ── FTP ────────────────────────────────────────────────────────────────────

    @property
    def ftp(self) -> int | None:
        """Current FTP — the most recent FTPHistory entry."""
        return self.ftp_history.order_by("-effective_date").values_list("ftp", flat=True).first()

    def ftp_on_date(self, date: _dt.date) -> int | None:
        """FTP effective on *date* (most recent entry with effective_date ≤ date)."""
        return (
            self.ftp_history.filter(effective_date__lte=date)
            .order_by("-effective_date")
            .values_list("ftp", flat=True)
            .first()
        )

    def record_ftp(
        self,
        ftp: int,
        effective_date: _dt.date | None = None,
        source: str = "manual",
        notes: str = "",
    ) -> "FTPHistory":
        """Create or update an FTP history entry for the given date."""
        if effective_date is None:
            effective_date = _dt.date.today()
        entry, _ = FTPHistory.objects.update_or_create(
            user=self,
            effective_date=effective_date,
            defaults={"ftp": ftp, "source": source, "notes": notes},
        )
        return entry

    # ── Weight ─────────────────────────────────────────────────────────────────

    @property
    def weight_kg(self):
        """Current weight — the most recent WeightHistory entry."""
        return (
            self.weight_history.order_by("-effective_date")
            .values_list("weight_kg", flat=True)
            .first()
        )

    def weight_on_date(self, date: _dt.date):
        """Weight effective on *date*."""
        return (
            self.weight_history.filter(effective_date__lte=date)
            .order_by("-effective_date")
            .values_list("weight_kg", flat=True)
            .first()
        )

    def record_weight(self, weight_kg, effective_date: _dt.date | None = None) -> "WeightHistory":
        """Create or update a weight history entry for the given date."""
        if effective_date is None:
            effective_date = _dt.date.today()
        entry, _ = WeightHistory.objects.update_or_create(
            user=self,
            effective_date=effective_date,
            defaults={"weight_kg": weight_kg},
        )
        return entry

    # ── Derived ────────────────────────────────────────────────────────────────

    @property
    def watts_per_kg(self):
        ftp = self.ftp
        weight = self.weight_kg
        if ftp and weight:
            return round(float(ftp) / float(weight), 2)
        return None

    @property
    def strava_connected(self):
        return bool(self.strava_athlete_id and self.strava_refresh_token)

    def __str__(self):
        return self.username


# ── History tables ─────────────────────────────────────────────────────────────


class FTPSource(models.TextChoices):
    MANUAL = "manual", "Manual entry"
    RAMP_TEST = "ramp_test", "Ramp test"
    TWENTY_MIN_TEST = "20min_test", "20-minute test"
    EIGHT_MIN_TEST = "8min_test", "8-minute test"
    AI_ESTIMATE = "ai_estimate", "AI estimate"
    STRAVA_ESTIMATE = "strava_estimate", "Strava estimate"
    RACE_RESULT = "race_result", "Race result"


class FTPHistory(models.Model):
    """One row per FTP measurement.  The most-recent entry (by effective_date)
    is the user's current FTP, exposed via ``User.ftp``."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ftp_history",
    )
    ftp = models.PositiveIntegerField(help_text="FTP in watts")
    effective_date = models.DateField(help_text="Date this FTP became effective")
    source = models.CharField(
        max_length=30,
        choices=FTPSource.choices,
        default=FTPSource.MANUAL,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date"]
        unique_together = [["user", "effective_date"]]
        verbose_name = "FTP history entry"
        verbose_name_plural = "FTP history"

    def __str__(self):
        return f"{self.user} — {self.ftp}W on {self.effective_date} ({self.get_source_display()})"


class WeightHistory(models.Model):
    """One row per weight measurement.  The most-recent entry is exposed via
    ``User.weight_kg``.  Recorded automatically when the user saves their
    profile with a new weight."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weight_history",
    )
    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        help_text="Body weight in kg",
    )
    effective_date = models.DateField(help_text="Date of this measurement")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date"]
        unique_together = [["user", "effective_date"]]
        verbose_name = "Weight history entry"
        verbose_name_plural = "Weight history"

    def __str__(self):
        return f"{self.user} — {self.weight_kg}kg on {self.effective_date}"
