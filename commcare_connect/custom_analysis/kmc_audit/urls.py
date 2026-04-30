"""URL configuration for the KMC Audit Dashboard sub-app."""

from django.urls import path

from commcare_connect.custom_analysis.kmc_audit import views

app_name = "kmc_audit"

urlpatterns = [
    path("", views.KMCAuditDashboardView.as_view(), name="dashboard"),
    path(
        "flw/<int:opportunity_id>/<str:username>/",
        views.KMCFLWDrilldownView.as_view(),
        name="flw_drilldown",
    ),
    path("audit_modal/", views.KMCAuditModalView.as_view(), name="audit_modal"),
    path("create_audit/", views.KMCAuditCreateView.as_view(), name="create_audit"),
    path("flag_catalogue/", views.KMCFlagCatalogueView.as_view(), name="flag_catalogue"),
]
