from django.contrib import admin
from .models import Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "source", "sport_type", "start_datetime",
                    "duration_formatted", "average_watts", "tss"]
    list_filter = ["source", "sport_type"]
    search_fields = ["name", "user__username"]
    readonly_fields = ["raw_data", "synced_at"]

    def duration_formatted(self, obj):
        return obj.duration_formatted
