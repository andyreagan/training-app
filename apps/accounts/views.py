import datetime

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .forms import LoginForm, ProfileForm, ProgressionScoresForm, RegisterForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        login(request, user)
        # Create default progression scores
        from apps.plans.models import UserProgressionScores
        UserProgressionScores.objects.get_or_create(user=user)
        messages.success(request, "Welcome! Set your FTP and progression scores in your profile.")
        return redirect("profile")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get("next", "dashboard"))
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):
    from apps.plans.models import UserProgressionScores
    scores_obj, _ = UserProgressionScores.objects.get_or_create(user=request.user)

    profile_form = ProfileForm(
        request.POST if request.method == "POST" and "save_profile" in request.POST else None,
        instance=request.user,
    )
    scores_form = ProgressionScoresForm(
        request.POST if request.method == "POST" and "save_scores" in request.POST else None,
        scores_instance=scores_obj,
    )

    if request.method == "POST":
        if "save_profile" in request.POST and profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")

        if "save_scores" in request.POST and scores_form.is_valid():
            for key in scores_obj.SCORE_FIELDS:
                scores_obj.set_score(key, scores_form.cleaned_data[f"{key}_score"])
            scores_obj.save()
            messages.success(request, "Progression scores updated.")
            return redirect("profile")

    rung_summary = scores_obj.rung_summary()
    return render(request, "accounts/profile.html", {
        "profile_form": profile_form,
        "scores_form": scores_form,
        "rung_summary": rung_summary,
        "scores_obj": scores_obj,
    })


@login_required
def dashboard_view(request):
    from apps.scheduler.models import ScheduledWorkout
    from apps.integrations.models import Activity
    from apps.plans.models import UserProgressionScores

    today = datetime.date.today()
    upcoming = (
        ScheduledWorkout.objects.filter(user=request.user, date__gte=today)
        .select_related("workout")
        .order_by("date")[:7]
    )
    recent_activities = (
        Activity.objects.filter(user=request.user).order_by("-start_datetime")[:5]
    )
    this_week_start = today - datetime.timedelta(days=today.weekday())
    this_week_workouts = ScheduledWorkout.objects.filter(
        user=request.user,
        date__gte=this_week_start,
        date__lte=this_week_start + datetime.timedelta(days=6),
    ).select_related("workout")

    scores_obj, _ = UserProgressionScores.objects.get_or_create(user=request.user)

    context = {
        "upcoming": upcoming,
        "recent_activities": recent_activities,
        "this_week_workouts": this_week_workouts,
        "today": today,
        "rung_summary": scores_obj.rung_summary(),
        "ftp": request.user.ftp,
    }
    return render(request, "dashboard.html", context)
