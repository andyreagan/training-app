import datetime
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.plans.models import WorkoutBlock
from .models import ScheduledWorkout


@login_required
def calendar_view(request):
    workouts = WorkoutBlock.objects.all().order_by("category", "name")
    return render(request, "scheduler/calendar.html", {"workouts": workouts})


@login_required
def calendar_events_api(request):
    """JSON endpoint consumed by FullCalendar."""
    start = request.GET.get("start")
    end = request.GET.get("end")

    qs = ScheduledWorkout.objects.filter(user=request.user).select_related("workout")
    if start:
        qs = qs.filter(date__gte=start[:10])
    if end:
        qs = qs.filter(date__lte=end[:10])

    events = []
    for sw in qs:
        events.append(
            {
                "id": sw.pk,
                "title": sw.workout.name,
                "start": sw.date.isoformat(),
                "color": sw.workout.color,
                "extendedProps": {
                    "category": sw.workout.category_label,
                    "duration_minutes": sw.workout.total_duration_minutes,
                    "tss": sw.workout.tss_estimate,
                    "completed": sw.completed,
                    "notes": sw.notes,
                    "workout_id": sw.workout.pk,
                    "workout_slug": sw.workout.slug,
                },
            }
        )
    return JsonResponse(events, safe=False)


@login_required
@require_POST
def add_workout(request):
    """
    Add a workout block to a calendar date.
    Accepts both JSON (from the calendar JS) and form POST (from workout detail page).
    """
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            data = json.loads(request.body)
            date = datetime.date.fromisoformat(data["date"])
            workout = get_object_or_404(WorkoutBlock, pk=data["workout_id"])
            notes = data.get("notes", "")
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        as_json = True
    else:
        # Form POST from workout detail page
        try:
            date = datetime.date.fromisoformat(request.POST["date"])
            workout = get_object_or_404(WorkoutBlock, pk=request.POST["workout_id"])
            notes = request.POST.get("notes", "")
        except (KeyError, ValueError) as e:
            from django.contrib import messages
            messages.error(request, f"Could not add workout: {e}")
            return redirect("calendar")
        as_json = False

    sw = ScheduledWorkout.objects.create(
        user=request.user,
        workout=workout,
        date=date,
        notes=notes,
    )

    if not as_json:
        from django.contrib import messages
        messages.success(request, f"Added {workout.name} to {date}.")
        return redirect("calendar")

    return JsonResponse({
        "id": sw.pk,
        "title": workout.name,
        "start": date.isoformat(),
        "color": workout.color,
        "extendedProps": {
            "category": workout.category_label,
            "duration_minutes": workout.total_duration_minutes,
            "tss": workout.tss_estimate,
            "completed": sw.completed,
            "notes": sw.notes,
            "workout_id": workout.pk,
            "workout_slug": workout.slug,
        },
    })


@login_required
@require_POST
def move_workout(request, pk):
    """Drag-and-drop reschedule."""
    sw = get_object_or_404(ScheduledWorkout, pk=pk, user=request.user)
    try:
        data = json.loads(request.body)
        sw.date = datetime.date.fromisoformat(data["date"])
        sw.save()
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"status": "ok", "date": sw.date.isoformat()})


@login_required
@require_POST
def delete_workout(request, pk):
    sw = get_object_or_404(ScheduledWorkout, pk=pk, user=request.user)
    sw.delete()
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def toggle_complete(request, pk):
    sw = get_object_or_404(ScheduledWorkout, pk=pk, user=request.user)
    sw.completed = not sw.completed
    sw.save()
    return JsonResponse({"status": "ok", "completed": sw.completed})


@login_required
def populate_from_plan(request):
    """Populate the calendar from the user's active plan starting at their chosen start date."""
    from apps.plans.models import UserPlan

    active = UserPlan.objects.filter(user=request.user, is_active=True).select_related("plan").first()
    if not active:
        from django.contrib import messages
        messages.warning(request, "You don't have an active training plan. Select one first.")
        return redirect("plan_list")

    if request.method == "POST":
        # Delete existing scheduled workouts in the plan window if user confirms
        plan = active.plan
        start = active.start_date
        end = start + datetime.timedelta(weeks=plan.duration_weeks)

        overwrite = request.POST.get("overwrite") == "1"
        if overwrite:
            ScheduledWorkout.objects.filter(
                user=request.user, date__gte=start, date__lt=end
            ).delete()

        created = 0
        for pb in plan.planblock_set.select_related("workout"):
            # Monday = 0 baseline offset
            day_offset = (pb.week_number - 1) * 7 + pb.day_of_week
            workout_date = start + datetime.timedelta(days=day_offset)
            ScheduledWorkout.objects.get_or_create(
                user=request.user,
                workout=pb.workout,
                date=workout_date,
                defaults={"notes": f"From plan: {plan.name}"},
            )
            created += 1

        from django.contrib import messages
        messages.success(request, f"Added {created} workouts to your calendar.")
        return redirect("calendar")

    return render(
        request,
        "scheduler/populate_confirm.html",
        {"active_plan": active},
    )
