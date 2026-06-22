import datetime

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import FTPHistory, User


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
    weight_kg = forms.DecimalField(
        max_digits=5,
        decimal_places=1,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 70.5"}),
        help_text="Body weight in kg — used to compute W/kg. "
        "Changes are recorded in your weight history automatically.",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "max_hr", "resting_hr")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "max_hr": forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 185"}),
            "resting_hr": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 55"}
            ),
        }
        help_texts = {
            "max_hr": "Maximum heart rate in bpm.",
            "resting_hr": "Resting heart rate in bpm — used for HR-based training load.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill weight from history
        if self.instance and self.instance.pk:
            self.initial["weight_kg"] = self.instance.weight_kg


class FTPEntryForm(forms.ModelForm):
    """Form for adding / editing a single FTP history entry."""

    class Meta:
        model = FTPHistory
        fields = ("ftp", "effective_date", "source", "notes")
        widgets = {
            "ftp": forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 250"}),
            "effective_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"},
            ),
            "source": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Optional notes"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("effective_date") and not self.instance.pk:
            self.initial["effective_date"] = datetime.date.today()


class ProgressionScoresForm(forms.Form):
    """
    Lets the user manually set their per-zone progression scores (1.0–10.0).
    """

    ZONE_LABELS = [
        ("recovery", "Recovery"),
        ("endurance", "Endurance"),
        ("tempo", "Tempo"),
        ("sweet_spot", "Sweet Spot"),
        ("threshold", "Threshold"),
        ("vo2max", "VO2 Max"),
        ("anaerobic", "Anaerobic"),
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
                widget=forms.NumberInput(
                    attrs={
                        "class": "form-control form-control-sm",
                        "step": "0.1",
                        "min": "1.0",
                        "max": "10.0",
                    }
                ),
                help_text="1.0 = beginner, 5.0 = intermediate, 10.0 = world-class",
            )
