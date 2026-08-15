from django.urls import path

from childcare import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="cc-health"),
    path("dashboard/", views.DashboardModulesView.as_view(), name="cc-dashboard"),
    path("modules/<slug:module_key>/lessons/", views.LessonsByModuleView.as_view(), name="cc-lessons"),
    path("shorts/", views.ShortsListView.as_view(), name="cc-shorts"),
    path("friends/", views.FriendsListView.as_view(), name="cc-friends"),
    path("auth/register/", views.RegisterChildView.as_view(), name="cc-register"),
    path("auth/login/", views.LoginView.as_view(), name="cc-login"),
    path("auth/otp/send/", views.SendOtpView.as_view(), name="cc-otp-send"),
    path("auth/otp/verify/", views.VerifyOtpView.as_view(), name="cc-otp-verify"),
    path("auth/me/", views.MeView.as_view(), name="cc-me"),
    path("scores/sync/", views.SyncScoresView.as_view(), name="cc-scores-sync"),
    path("scores/leaderboard/", views.LeaderboardView.as_view(), name="cc-scores-leaderboard"),
]
