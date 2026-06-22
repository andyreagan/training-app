"""
Fatigue monitor views.

Collects TSS data via fatigue.queries, runs the Banister model,
and serves the results as a chart page and JSON APIs.
"""

import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from .banister import compute, tsb_color, tsb_zone
from .power import build_power_profile
from .queries import collect_activity_curves, collect_daily_tss


@login_required
def fatigue_dashboard(request):
    """Render the fatigue monitor chart page."""
    return render(request, "fatigue/dashboard.html")


@login_required
def fatigue_data_api(request):
    """
    GET /fatigue/api/data/?days_back=90&days_forward=30

    Returns JSON array of daily metrics for charting.
    """
    days_back = int(request.GET.get("days_back", 90))
    days_forward = int(request.GET.get("days_forward", 30))

    today = datetime.date.today()
    warmup_days = 60
    data_start = today - datetime.timedelta(days=days_back + warmup_days)
    visible_start = today - datetime.timedelta(days=days_back)
    end_date = today + datetime.timedelta(days=days_forward)

    inputs = collect_daily_tss(request.user, data_start, end_date)
    metrics = compute(inputs)

    visible = [m for m in metrics if m.date >= visible_start]

    return JsonResponse(
        [
            {
                "date": m.date.isoformat(),
                "tss": round(m.tss, 1),
                "ctl": m.ctl,
                "atl": m.atl,
                "tsb": m.tsb,
                "source": m.source,
                "zone": tsb_zone(m.tsb),
                "color": tsb_color(m.tsb),
            }
            for m in visible
        ],
        safe=False,
    )


@login_required
def calendar_tsb_api(request):
    """
    GET /fatigue/api/calendar-tsb/?start=...&end=...

    Returns TSB + zone color for each day, used by the calendar.
    """
    start = request.GET.get("start", "")
    end = request.GET.get("end", "")

    try:
        start_date = datetime.date.fromisoformat(start[:10])
        end_date = datetime.date.fromisoformat(end[:10])
    except (ValueError, IndexError):
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=30)
        end_date = today + datetime.timedelta(days=30)

    warmup_days = 60
    data_start = start_date - datetime.timedelta(days=warmup_days)

    inputs = collect_daily_tss(request.user, data_start, end_date)
    metrics = compute(inputs)

    result = {}
    for m in metrics:
        if m.date >= start_date:
            result[m.date.isoformat()] = {
                "tsb": m.tsb,
                "zone": tsb_zone(m.tsb),
                "color": tsb_color(m.tsb),
            }

    return JsonResponse(result)


@login_required
def power_profile_api(request):
    """
    GET /fatigue/api/power-profile/?days=30

    Merged power curve across activities in the window, with FTP estimate.
    """
    days = int(request.GET.get("days", 30))
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=days)

    activity_inputs = collect_activity_curves(request.user, start_date, today)
    profile = build_power_profile(activity_inputs)

    return JsonResponse(
        {
            "curve": [
                {
                    "duration": p.duration_seconds,
                    "watts": p.watts,
                    "source_date": p.source_date.isoformat(),
                    "source_name": p.source_name,
                }
                for p in profile.curve
            ],
            "ftp_estimate": {
                "ftp": profile.ftp_estimate.ftp,
                "method": profile.ftp_estimate.method,
                "duration_seconds": profile.ftp_estimate.duration_seconds,
                "raw_power": profile.ftp_estimate.raw_power,
            }
            if profile.ftp_estimate
            else None,
            "activity_count": profile.activity_count,
            "date_range": [profile.date_range[0].isoformat(), profile.date_range[1].isoformat()],
            "activities": [
                {
                    "date": inp.date.isoformat(),
                    "name": inp.activity_name,
                    "perceived_effort": inp.perceived_effort,
                    "tsb": inp.tsb,
                    "curve": [
                        {"duration": p.duration_seconds, "watts": p.watts} for p in inp.curve
                    ],
                }
                for inp in profile.activity_curves
            ],
        }
    )
