from django.views.static import serve
from django.conf.urls.static import static
from django.urls import path, re_path, include
from django.conf import settings
from rest_framework.routers import DefaultRouter
from . import views
from .views2 import DivisionsView, DistrictsView, ThanasView
from .views import (
    ItemListCreateView,
    CustomerCreateView,
    CustomerRetrieveView,
    SignupProfileView,
    MobileNumberExistsView,
    NotificationViewSet,
    PasswordExistsView,
    CustomerUpdateView,
    CustomerResetView,
    PasswordUpdateView,
    MobileUpdateView,
    CountryViewSet,
    AllCountriesView,
    SendVerificationCodeView,
    VerifyCodeView,
    SendPasswordResetCodeView,
    ResetPasswordWithCodeView,
    GenerateDefaultPasswordView,
    UpdateEmailView,
    UpdateWhatsAppApiKeyView,
    UniversityDepartmentsView,
    LocationDivisionsView,
    LocationDistrictsView,
    LocationThanasView,
    Merit5ViewSet,
    Merit6ViewSet,
    Merit7ViewSet,
    Vacancy5ViewSet,
    Vacancy6ViewSet,
    Vacancy7ViewSet,
    Recommend5ViewSet,
    Recommend6ViewSet,
    Recommend7ViewSet,
    BanbeisViewSet,
    InstitutesViewSet,
    TokenViewSet,
    InstituteDetailView,
)

router = DefaultRouter()
router.register(r'countries', CountryViewSet, basename='countries')
router.register(r'notification', NotificationViewSet, basename='notification')
# Job DB (cheradip_job) – NTRCA merit / vacancy / recommend / institutes / banbeis / token
router.register(r'merit5', Merit5ViewSet, basename='merit5')
router.register(r'merit6', Merit6ViewSet, basename='merit6')
router.register(r'merit7', Merit7ViewSet, basename='merit7')
router.register(r'vacancy5', Vacancy5ViewSet, basename='vacancy5')
router.register(r'vacancy6', Vacancy6ViewSet, basename='vacancy6')
router.register(r'vacancy7', Vacancy7ViewSet, basename='vacancy7')
router.register(r'recommend5', Recommend5ViewSet, basename='recommend5')
router.register(r'recommend6', Recommend6ViewSet, basename='recommend6')
router.register(r'recommend7', Recommend7ViewSet, basename='recommend7')
router.register(r'institutes', InstitutesViewSet, basename='institutes')
router.register(r'banbeis', BanbeisViewSet, basename='banbeis')
router.register(r'token', TokenViewSet, basename='token')

urlpatterns = [
    path('item/', ItemListCreateView.as_view(), name='item'),
    path('signup/', CustomerCreateView.as_view(), name='signup'),
    path('signup_profile/', SignupProfileView.as_view(), name='signup_profile'),
    path('login/', CustomerRetrieveView.as_view(), name='login'),
    path('profile_update/', CustomerUpdateView.as_view(), name='profile_update'),
    path('password_update/', PasswordUpdateView.as_view(), name='password_update'),
    path('mobile_update/', MobileUpdateView.as_view(), name='mobile_update'),
    path('password_reset/', CustomerResetView.as_view(), name='password_reset'),
    path('username/', MobileNumberExistsView.as_view(), name='username'),
    path('password/', PasswordExistsView.as_view(), name='password'),
    path('save_json_data/', views.save_json_data, name='save_json_data'),
    path('send_verification_code/', SendVerificationCodeView.as_view(), name='send_verification_code'),
    path('verify_code/', VerifyCodeView.as_view(), name='verify_code'),
    path('send_password_reset_code/', SendPasswordResetCodeView.as_view(), name='send_password_reset_code'),
    path('reset_password_with_code/', ResetPasswordWithCodeView.as_view(), name='reset_password_with_code'),
    path('generate_default_password/', GenerateDefaultPasswordView.as_view(), name='generate_default_password'),
    path('update_email/', UpdateEmailView.as_view(), name='update_email'),
    path('update_whatsapp_apikey/', UpdateWhatsAppApiKeyView.as_view(), name='update_whatsapp_apikey'),
    path('university_departments/', UniversityDepartmentsView.as_view(), name='university_departments'),
    path('country/', AllCountriesView.as_view(), name='country_list'),
    path('divisions/', DivisionsView.as_view(), name='divisions'),
    path('districts/', DistrictsView.as_view(), name='districts'),
    path('thanas/', ThanasView.as_view(), name='thanas'),
    path('locations/divisions/', LocationDivisionsView.as_view(), name='locations_divisions'),
    path('locations/districts/', LocationDistrictsView.as_view(), name='locations_districts'),
    path('locations/thanas/', LocationThanasView.as_view(), name='locations_thanas'),
    path('institute/', InstituteDetailView.as_view(), name='institute_detail'),
    path('sitemap.xml', views.sitemap_institutes),
    path('sitemap.xsl', views.sitemap_xsl),
    path('sitemap_pages.xml', views.sitemap_pages),
    path('sitemap_institutes_<int:page>.xml', views.sitemap_institutes_part),
    path('', include(router.urls)),
    re_path(r'^favicon\.ico$', serve, {'path': 'static/favicon.ico'}),
]

if settings.DEBUG:
    urlpatterns += static('/manage' + settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
