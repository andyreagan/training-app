import datetime
import os

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import FTPEntryForm, LoginForm, ProfileForm, ProgressionScoresForm, RegisterForm
from .models import FTPHistory

DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo1234")


def demo_login_view(request):
    """Auto-log in as the demo user and redirect to the dashboard."""
    # If already logged in as demo, just go to dashboard
    if request.user.is_authenticated and request.user.username == DEMO_USERNAME:
        return redirect("dashboard")

    # Log out any current session first
    if request.user.is_authenticated:
        logout(request)

    user = authenticate(request, username=DEMO_USERNAME, password=DEMO_PASSWORD)
    if user is None:
        messages.error(
            request,
            "Demo account is not available right now. Please try again in a moment.",
        )
        return redirect("login")

    login(request, user)
    return redirect("dashboard")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        login(request, user)
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
            # Record weight history if a new weight was provided
            new_weight = profile_form.cleaned_data.get("weight_kg")
            if new_weight is not None:
                current = request.user.weight_kg
                if current is None or new_weight != current:
                    request.user.record_weight(new_weight)
            messages.success(request, "Profile updated.")
            return redirect("profile")

        if "save_scores" in request.POST and scores_form.is_valid():
            for key in scores_obj.SCORE_FIELDS:
                scores_obj.set_score(key, scores_form.cleaned_data[f"{key}_score"])
            scores_obj.save()
            messages.success(request, "Progression scores updated.")
            return redirect("profile")

    rung_summary = scores_obj.rung_summary()
    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "scores_form": scores_form,
            "rung_summary": rung_summary,
            "scores_obj": scores_obj,
        },
    )


@login_required
def dashboard_view(request):
    from apps.integrations.models import Activity
    from apps.plans.models import UserProgressionScores
    from apps.scheduler.models import ScheduledWorkout

    today = datetime.date.today()
    upcoming = (
        ScheduledWorkout.objects.filter(user=request.user, date__gte=today)
        .select_related("workout")
        .order_by("date")[:7]
    )
    recent_activities = Activity.objects.filter(user=request.user).order_by("-start_datetime")[:5]
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


# ── FTP History ────────────────────────────────────────────────────────────────


@login_required
def ftp_history_view(request):
    """List and add FTP history entries."""
    entries = FTPHistory.objects.filter(user=request.user)
    form = FTPEntryForm(
        request.POST if request.method == "POST" and "add_ftp" in request.POST else None,
    )

    if request.method == "POST" and "add_ftp" in request.POST and form.is_valid():
        request.user.record_ftp(
            ftp=form.cleaned_data["ftp"],
            effective_date=form.cleaned_data["effective_date"],
            source=form.cleaned_data["source"],
            notes=form.cleaned_data.get("notes", ""),
        )
        messages.success(request, f"FTP {form.cleaned_data['ftp']}W recorded.")
        return redirect("ftp_history")

    return render(
        request,
        "accounts/ftp_history.html",
        {"entries": entries, "form": form},
    )


@login_required
def ftp_history_edit(request, pk):
    """Edit a single FTP history entry."""
    entry = get_object_or_404(FTPHistory, pk=pk, user=request.user)
    form = FTPEntryForm(request.POST or None, instance=entry)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "FTP entry updated.")
        return redirect("ftp_history")

    return render(
        request,
        "accounts/ftp_history_edit.html",
        {"form": form, "entry": entry},
    )


@login_required
def ftp_history_delete(request, pk):
    """Delete a single FTP history entry."""
    entry = get_object_or_404(FTPHistory, pk=pk, user=request.user)
    if request.method == "POST":
        entry.delete()
        messages.success(request, "FTP entry deleted.")
    return redirect("ftp_history")
