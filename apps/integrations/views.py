from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Activity


@login_required
def integrations_home(request):
    recent = Activity.objects.filter(user=request.user).order_by("-start_datetime")[:20]
    return render(request, "integrations/home.html", {
        "recent_activities": recent,
        "strava_connected": request.user.strava_connected,
    })
