from django.views.static import serve
from django.conf.urls.static import static
from django.urls import path, re_path
from django.conf import settings
from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import (
    ItemListCreateView,
    DivisionsView,
    DistrictsView,
    ThanasView,
    CustomerCreateView,
    CustomerRetrieveView,
    MobileNumberExistsView,
    NotificationExistsView,
    PasswordExistsView,
    CustomerUpdateView,
    CustomerResetView,
    PasswordUpdateView,
    MobileUpdateView,
    OrderRetrieveView,
    VacancyViewSet,
    MeritViewSet,
    Vacancy5ViewSet,
    Merit5ViewSet,
    BanbeisViewSet,
    RecommendViewSet,
    TokenViewSet,
    InstitutesViewSet
)

router = DefaultRouter()
router.register(r'token', TokenViewSet, basename='token')
router.register(r'vacant6', VacancyViewSet, basename='vacancy6')
router.register(r'merit', MeritViewSet, basename='merit')
router.register(r'vacant5', VacancyViewSet, basename='vacancy5')
router.register(r'merit5', Merit5ViewSet, basename='merit5')
router.register(r'recommend', RecommendViewSet, basename='recommend')
router.register(r'institute', BanbeisViewSet, basename='institute')
router.register(r'institutes', InstitutesViewSet, basename='institutes')

urlpatterns = [
    path('item/', ItemListCreateView.as_view(), name='item'),
    path('divisions/', DivisionsView.as_view(), name='divisions'),
    path('districts/', DistrictsView.as_view(), name='districts'),
    path('thanas/', ThanasView.as_view(), name='thanas'),
    path('signup/', CustomerCreateView.as_view(), name='signup'),
    path('login/', CustomerRetrieveView.as_view(), name='login'),
    path('profile_update/', CustomerUpdateView.as_view(), name='profile_update'),
    path('password_update/', PasswordUpdateView.as_view(), name='password_update'),
    path('mobile_update/', MobileUpdateView.as_view(), name='mobile_update'),
    path('password_reset/', CustomerResetView.as_view(), name='password_reset'),
    path('username/', MobileNumberExistsView.as_view(), name='username'),
    path('password/', PasswordExistsView.as_view(), name='password'),
    path('notification/', NotificationExistsView.as_view(), name='notification'),
    path('myorder/<str:username>/', OrderRetrieveView.as_view(), name='myorder'),
    path('save_json_data/', views.save_json_data, name='save_json_data'),
    path('', include(router.urls)),
    re_path(
        r'^favicon\.ico$',
        serve,
        {'document_root': settings.BASE_DIR, 'path': 'favicon.ico'},
    ),
    # re_path(r'^manage/media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),
]

if settings.DEBUG:
    urlpatterns += static('/manage' + settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) #for Hosting
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT, show_indexes=True) #for Hosting

# if settings.DEBUG:
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


