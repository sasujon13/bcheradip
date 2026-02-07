from django.views.static import serve
from django.conf.urls.static import static
from django.urls import path, re_path
from django.conf import settings
from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views2 import DivisionsView, DistrictsView, ThanasView
from .views import (
    ItemListCreateView,
    CustomerCreateView,
    CustomerRetrieveView,
    MobileNumberExistsView,
    NotificationViewSet,
    PasswordExistsView,
    CustomerUpdateView,
    CustomerResetView,
    PasswordUpdateView,
    MobileUpdateView,
    OrderRetrieveView,
    VacancyViewSet,
    Vacancy5ViewSet,
    Vacancy6ViewSet,
    MeritViewSet,
    Merit5ViewSet,
    Merit6ViewSet,
    BanbeisViewSet,
    RecommendViewSet,
    Recommend5ViewSet,
    Recommend6ViewSet,
    TokenViewSet,
    InstitutesViewSet,
    # GetRequisitionsView,  # TODO: View not implemented yet
    # MCQ and Related ViewSets
    GroupViewSet,
    SubjectViewSet,
    ChapterViewSet,
    TopicViewSet,
    InstituteViewSet,
    YearViewSet,
    McqIctViewSet,
    # Country ViewSet + flat list for dropdowns
    CountryViewSet,
    AllCountriesView,
    # Verification Views (Email + WhatsApp)
    SendVerificationCodeView,
    VerifyCodeView,
    SendPasswordResetCodeView,
    ResetPasswordWithCodeView,
    GenerateDefaultPasswordView,
    UpdateEmailView,
    UpdateWhatsAppApiKeyView,
    GetGroupsByClassView,
    GetDepartmentsView,
    GetClassInfoView,
)

router = DefaultRouter()
# Country API: GET /api/countries/, /api/countries/{code}/, /api/countries/detect/, /api/countries/featured/ (CHERADIP_PROJECT.md § Country Autocomplete API)
router.register(r'countries', CountryViewSet, basename='countries')
router.register(r'token', TokenViewSet, basename='token')
router.register(r'merit', MeritViewSet, basename='merit')
router.register(r'merit5', Merit5ViewSet, basename='merit5')
router.register(r'merit6', Merit6ViewSet, basename='merit6')
router.register(r'vacant', VacancyViewSet, basename='vacant')
router.register(r'vacant5', Vacancy5ViewSet, basename='vacant5')
router.register(r'vacant6', Vacancy6ViewSet, basename='vacant6')
router.register(r'recommend', RecommendViewSet, basename='recommend')
router.register(r'recommend5', Recommend5ViewSet, basename='recommend5')
router.register(r'recommend6', Recommend6ViewSet, basename='recommend6')
router.register(r'institute', BanbeisViewSet, basename='institute')
router.register(r'institutes', InstitutesViewSet, basename='institutes')

# MCQ and Related Endpoints
router.register(r'groups', GroupViewSet, basename='groups')
router.register(r'subjects', SubjectViewSet, basename='subjects')
router.register(r'chapters', ChapterViewSet, basename='chapters')
router.register(r'topics', TopicViewSet, basename='topics')
router.register(r'instituteTypes', InstituteViewSet, basename='instituteTypes')  # Alias for frontend compatibility
router.register(r'years', YearViewSet, basename='years')
router.register(r'questions', McqIctViewSet, basename='questions')  # Main endpoint for MCQ questions
router.register(r'notification', NotificationViewSet, basename='notification')

urlpatterns = [
    path('item/', ItemListCreateView.as_view(), name='item'),
    path('signup/', CustomerCreateView.as_view(), name='signup'),
    path('login/', CustomerRetrieveView.as_view(), name='login'),
    path('profile_update/', CustomerUpdateView.as_view(), name='profile_update'),
    path('password_update/', PasswordUpdateView.as_view(), name='password_update'),
    path('mobile_update/', MobileUpdateView.as_view(), name='mobile_update'),
    path('password_reset/', CustomerResetView.as_view(), name='password_reset'),
    path('username/', MobileNumberExistsView.as_view(), name='username'),
    path('password/', PasswordExistsView.as_view(), name='password'),
    path('myorder/<str:username>/', OrderRetrieveView.as_view(), name='myorder'),
    path('save_json_data/', views.save_json_data, name='save_json_data'),
    # path('get_requisition_report_ngi3.php', GetRequisitionsView.as_view(), name='get_requisition_report'),  # TODO: View not implemented
    
    # Verification Endpoints (Email + WhatsApp - FREE)
    path('send_verification_code/', SendVerificationCodeView.as_view(), name='send_verification_code'),
    path('verify_code/', VerifyCodeView.as_view(), name='verify_code'),
    path('send_password_reset_code/', SendPasswordResetCodeView.as_view(), name='send_password_reset_code'),
    path('reset_password_with_code/', ResetPasswordWithCodeView.as_view(), name='reset_password_with_code'),
    path('generate_default_password/', GenerateDefaultPasswordView.as_view(), name='generate_default_password'),
    path('update_email/', UpdateEmailView.as_view(), name='update_email'),
    path('update_whatsapp_apikey/', UpdateWhatsAppApiKeyView.as_view(), name='update_whatsapp_apikey'),
    
    # Class, Group, and Department Endpoints
    path('class_info/', GetClassInfoView.as_view(), name='class_info'),
    path('groups_by_class/', GetGroupsByClassView.as_view(), name='groups_by_class'),
    path('departments/', GetDepartmentsView.as_view(), name='departments'),
    # All countries as array for <option> dropdowns (GET /api/country/)
    path('country/', AllCountriesView.as_view(), name='country_list'),
    # Bangladesh location dropdowns (used by auth, profile, order, etc.)
    path('divisions/', DivisionsView.as_view(), name='divisions'),
    path('districts/', DistrictsView.as_view(), name='districts'),
    path('thanas/', ThanasView.as_view(), name='thanas'),
    path('', include(router.urls)),
    re_path(r'^favicon\.ico$', serve, {'path': 'static/favicon.ico'}),
    # re_path(r'^manage/media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),
]

if settings.DEBUG:
    urlpatterns += static('/manage' + settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) #for Hosting
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT, show_indexes=True) #for Hosting

# if settings.DEBUG:
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


