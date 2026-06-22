from django.contrib import admin

from .models import ScheduledWorkout


@admin.register(ScheduledWorkout)
class ScheduledWorkoutAdmin(admin.ModelAdmin):
    list_display = ["user", "workout", "date", "completed"]
    list_filter = ["completed", "date"]
    raw_id_fields = ["user", "activity"]
