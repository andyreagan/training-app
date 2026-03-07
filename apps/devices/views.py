from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404

from apps.plans.models import WorkoutBlock
from .generators import generate_zwo, generate_erg, generate_fit

FORMATS = {
    "zwo": ("application/xml",        ".zwo", generate_zwo),
    "erg": ("text/plain",             ".erg", generate_erg),
    "fit": ("application/octet-stream", ".fit", generate_fit),
}


@login_required
def download_workout(request, pk, fmt):
    """
    Download a workout file for a device.

    The interval structure comes from the WorkoutBlock's progression score.
    Absolute power targets are computed from the athlete's FTP (defaults to
    250 W if none is set — the reference FTP used throughout the system).
    """
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise Http404(f"Unknown format: {fmt!r}")

    workout = get_object_or_404(WorkoutBlock, pk=pk)
    content_type, ext, generator = FORMATS[fmt]

    ftp = request.user.ftp or 250
    data = generator(workout, ftp=ftp)

    filename = f"{workout.slug}{ext}"
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
