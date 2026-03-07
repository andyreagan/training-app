from django.conf import settings
from django.db import models

from apps.plans.models import WorkoutBlock


class ScheduledWorkout(models.Model):
    """A workout block placed on a specific date for a specific user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scheduled_workouts"
    )
    workout = models.ForeignKey(WorkoutBlock, on_delete=models.CASCADE)
    date = models.DateField()
    notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)

    # Linked activity from a data source (Strava, Garmin, …)
    activity = models.OneToOneField(
        "integrations.Activity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_workout",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "created_at"]
        # Allow multiple workouts per day (e.g. AM/PM)

    def __str__(self):
        return f"{self.user} — {self.workout.name} on {self.date}"
