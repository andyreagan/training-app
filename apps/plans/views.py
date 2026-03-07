import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import TrainingPlan, UserPlan, WorkoutBlock


def plan_list(request):
    plans = TrainingPlan.objects.filter(is_published=True)
    active_plan = None
    if request.user.is_authenticated:
        active_plan = UserPlan.objects.filter(user=request.user, is_active=True).first()
    return render(request, "plans/list.html", {"plans": plans, "active_plan": active_plan})


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def plan_detail(request, slug):
    plan = get_object_or_404(TrainingPlan, slug=slug, is_published=True)
    active_user_plan = None
    if request.user.is_authenticated:
        active_user_plan = UserPlan.objects.filter(
            user=request.user, plan=plan, is_active=True
        ).first()

    # Convert weekly_structure {week: {dow: [PlanBlock]}} into a list of rows
    # that are easy to iterate in the template without needing variable dict lookups.
    # Each row: {"week": N, "phase": str, "days": [{"name": str, "blocks": [...]}]}
    raw = plan.weekly_structure
    weekly_rows = []
    for week_num, days in raw.items():
        if week_num <= 4:
            phase = ("Foundation", "secondary")
        elif week_num <= 10:
            phase = ("Base", "primary")
        elif week_num <= 16:
            phase = ("Build", "warning")
        else:
            phase = ("Peak", "danger")
        day_cells = [
            {"name": DAY_NAMES[dow], "blocks": days.get(dow, [])}
            for dow in range(7)
        ]
        weekly_rows.append({"week": week_num, "phase": phase, "days": day_cells})

    return render(request, "plans/detail.html", {
        "plan": plan,
        "weekly_rows": weekly_rows,
        "active_user_plan": active_user_plan,
    })


@login_required
def adopt_plan(request, slug):
    plan = get_object_or_404(TrainingPlan, slug=slug, is_published=True)
    if request.method == "POST":
        start_date_str = request.POST.get("start_date")
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
        except (ValueError, TypeError):
            start_date = datetime.date.today()

        up, created = UserPlan.objects.get_or_create(
            user=request.user, plan=plan, defaults={"start_date": start_date}
        )
        if not created:
            up.start_date = start_date
            up.is_active = True
            up.save()
        up.deactivate_others()

        messages.success(request, f"You're now following \"{plan.name}\". Starting {start_date}.")
        return redirect("calendar")
    return redirect("plan_detail", slug=slug)


@login_required
def unadopt_plan(request, slug):
    plan = get_object_or_404(TrainingPlan, slug=slug)
    if request.method == "POST":
        UserPlan.objects.filter(user=request.user, plan=plan).update(is_active=False)
        messages.info(request, f"Removed \"{plan.name}\" from your active plan.")
    return redirect("plan_list")


def workout_detail(request, pk):
    workout = get_object_or_404(WorkoutBlock, pk=pk)
    ftp = getattr(request.user, "ftp", None) or 250 if request.user.is_authenticated else 250

    def fmt_seconds(s):
        if s >= 3600:
            h, rem = divmod(s, 3600)
            return f"{h}h {rem // 60}m"
        if s >= 60:
            m, sec = divmod(s, 60)
            return f"{m}m" if sec == 0 else f"{m}m {sec}s"
        return f"{s}s"

    steps = []
    for step in workout.structure:
        s = dict(step)
        s["duration_display"] = fmt_seconds(step["duration_seconds"])
        s["watts_low"]  = round(ftp * step["power_low"]  / 100)
        s["watts_high"] = round(ftp * step["power_high"] / 100)
        if "rest_duration_seconds" in step:
            s["rest_duration_display"] = fmt_seconds(step["rest_duration_seconds"])
            s["rest_watts_low"]  = round(ftp * step.get("rest_power_low",  35) / 100)
            s["rest_watts_high"] = round(ftp * step.get("rest_power_high", 52) / 100)
        steps.append(s)

    return render(request, "plans/workout_detail.html", {
        "workout": workout,
        "steps": steps,
        "ftp": ftp,
    })
