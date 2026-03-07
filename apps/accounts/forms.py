from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "ftp", "max_hr", "weight_kg")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name":  forms.TextInput(attrs={"class": "form-control"}),
            "email":      forms.EmailInput(attrs={"class": "form-control"}),
            "ftp":        forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 250"}),
            "max_hr":     forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 185"}),
            "weight_kg":  forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 70.5"}),
        }
        help_texts = {
            "ftp":       "Functional Threshold Power in watts. All workout intensities scale from this.",
            "max_hr":    "Maximum heart rate in bpm.",
            "weight_kg": "Body weight in kg — used to compute W/kg.",
        }


class ProgressionScoresForm(forms.Form):
    """
    Lets the user manually set their per-zone progression scores (1.0–10.0).
    The score determines which rung of each zone's ladder they're currently on.
    A score of 5.0 is the 'plain FTP' midpoint — a safe default before any
    training history exists.
    """
    ZONE_LABELS = [
        ("recovery",   "Recovery"),
        ("endurance",  "Endurance"),
        ("tempo",      "Tempo"),
        ("sweet_spot", "Sweet Spot"),
        ("threshold",  "Threshold"),
        ("vo2max",     "VO2 Max"),
        ("anaerobic",  "Anaerobic"),
    ]

    def __init__(self, *args, scores_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in self.ZONE_LABELS:
            current = getattr(scores_instance, f"{key}_score", 5.0) if scores_instance else 5.0
            self.fields[f"{key}_score"] = forms.FloatField(
                label=label,
                min_value=1.0,
                max_value=10.0,
                initial=current,
                widget=forms.NumberInput(attrs={
                    "class": "form-control form-control-sm",
                    "step": "0.1",
                    "min": "1.0",
                    "max": "10.0",
                }),
                help_text="1.0 = beginner, 5.0 = intermediate, 10.0 = world-class",
            )
