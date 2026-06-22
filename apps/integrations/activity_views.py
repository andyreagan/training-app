"""
Activity detail views — power chart, effort rating, FTP estimation.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.fatigue.banister import tsb_zone
from apps.fatigue.hr import adjust_ftp_for_hr
from apps.fatigue.power import compute_power_curve, compute_rolling_average, estimate_ftp
from apps.fatigue.queries import tsb_for_date

from .models import Activity


@login_required
def activity_detail(request, pk):
    """Render the activity detail page with power chart and effort rating."""
    activity = get_object_or_404(Activity, pk=pk, user=request.user)

    # Get TSB on the activity date for fatigue context
    tsb_on_day = tsb_for_date(request.user, activity.start_datetime.date())

    # FTP estimate if we have power data
    ftp_est = None
    ftp_hr_adjusted = None
    if activity.has_power_stream:
        ftp_est = estimate_ftp(activity.power_data["watts"])

        # HR-adjusted FTP if we have both power and HR
        if ftp_est and activity.average_hr and request.user.max_hr:
            resting_hr = request.user.resting_hr or 60
            ftp_hr_adjusted = adjust_ftp_for_hr(
                ftp_raw=ftp_est.ftp,
                avg_hr=activity.average_hr,
                max_hr=request.user.max_hr,
                resting_hr=resting_hr,
            )

    return render(
        request,
        "integrations/activity_detail.html",
        {
            "activity": activity,
            "tsb_on_day": tsb_on_day,
            "tsb_zone": tsb_zone(tsb_on_day) if tsb_on_day is not None else None,
            "ftp_estimate": ftp_est,
            "ftp_hr_adjusted": ftp_hr_adjusted,
        },
    )


@login_required
def activity_power_api(request, pk):
    """
    GET /integrations/activity/<pk>/api/power/

    Returns JSON with smoothed power trace, power curve, and FTP estimate.
    """
    activity = get_object_or_404(Activity, pk=pk, user=request.user)

    if not activity.has_power_stream:
        return JsonResponse({"error": "No power data"}, status=404)

    watts = activity.power_data["watts"]
    time_data = activity.power_data.get("time", list(range(len(watts))))

    smoothed = compute_rolling_average(watts, window_seconds=30)
    curve = compute_power_curve(watts)
    ftp_est = estimate_ftp(watts)

    return JsonResponse(
        {
            "time": time_data,
            "watts_raw": watts,
            "watts_smoothed": smoothed,
            "power_curve": [{"duration": p.duration_seconds, "watts": p.watts} for p in curve],
            "ftp_estimate": {
                "ftp": ftp_est.ftp,
                "method": ftp_est.method,
                "duration_seconds": ftp_est.duration_seconds,
                "raw_power": ftp_est.raw_power,
            }
            if ftp_est
            else None,
            "duration_seconds": len(watts),
        }
    )


@login_required
@require_POST
def rate_effort(request, pk):
    """POST /integrations/activity/<pk>/rate/ — set perceived effort 1–10."""
    activity = get_object_or_404(Activity, pk=pk, user=request.user)

    try:
        effort = int(request.POST.get("perceived_effort", 0))
        if not 1 <= effort <= 10:
            raise ValueError("Must be 1–10")
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": str(e)}, status=400)

    activity.perceived_effort = effort
    activity.effort_source = "manual"
    activity.save(update_fields=["perceived_effort", "effort_source"])

    return JsonResponse(
        {
            "status": "ok",
            "perceived_effort": activity.perceived_effort,
            "effort_label": activity.effort_label,
        }
    )
