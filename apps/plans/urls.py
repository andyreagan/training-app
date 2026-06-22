from django.urls import path

from . import views

urlpatterns = [
    path("", views.plan_list, name="plan_list"),
    path("<slug:slug>/", views.plan_detail, name="plan_detail"),
    path("<slug:slug>/adopt/", views.adopt_plan, name="adopt_plan"),
    path("<slug:slug>/unadopt/", views.unadopt_plan, name="unadopt_plan"),
    path("workout/<int:pk>/", views.workout_detail, name="workout_detail"),
]
