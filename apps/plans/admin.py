from django.contrib import admin
from .models import WorkoutBlock, TrainingPlan, PlanBlock, UserPlan, UserProgressionScores


class PlanBlockInline(admin.TabularInline):
    model = PlanBlock
    extra = 1
    autocomplete_fields = ["workout"]


@admin.register(WorkoutBlock)
class WorkoutBlockAdmin(admin.ModelAdmin):
    list_display = [
        "name", "category", "progression_score", "total_duration_minutes",
        "tss_estimate", "rung_summary",
    ]
    list_filter = ["category"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["total_duration_minutes", "tss_estimate", "structure_preview"]

    def rung_summary(self, obj):
        return obj.rung.summary()
    rung_summary.short_description = "Interval Structure"

    def structure_preview(self, obj):
        lines = [f"<strong>{s['label']}</strong>: {s['type']} {s['duration_seconds']//60} min "
                 f"@ {s['power_low']}–{s['power_high']}% FTP"
                 + (f" ×{s['repeat']}" if s.get("repeat", 1) > 1 else "")
                 for s in obj.structure]
        from django.utils.html import format_html
        return format_html("<br>".join(lines))
    structure_preview.short_description = "Computed Structure"


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "duration_weeks", "target_hours_per_week_low",
                    "target_hours_per_week_high", "is_published"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PlanBlockInline]


@admin.register(PlanBlock)
class PlanBlockAdmin(admin.ModelAdmin):
    list_display = ["plan", "week_number", "day_of_week", "workout", "order"]
    list_filter = ["plan"]


@admin.register(UserPlan)
class UserPlanAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "start_date", "is_active"]
    list_filter = ["is_active"]


@admin.register(UserProgressionScores)
class UserProgressionScoresAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "recovery_score", "endurance_score", "tempo_score",
        "sweet_spot_score", "threshold_score", "vo2max_score", "anaerobic_score",
        "updated_at",
    ]
    readonly_fields = ["updated_at"]
