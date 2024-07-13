from django.views.static import serve
from django.conf.urls.static import static
from django.urls import path, re_path
from django.conf import settings
from . import views
from .views import (
    ItemListCreateView,
    DivisionsView,
    DistrictsView,
    ThanasView,
    CustomerCreateView,
    CustomerRetrieveView,
    MobileNumberExistsView,
    PasswordExistsView,
    CustomerUpdateView,
    CustomerResetView,
    PasswordUpdateView,
    OrderRetrieveView,
    
)
urlpatterns = [
    path('item/', ItemListCreateView.as_view(), name='item'),
    path('divisions/', DivisionsView.as_view(), name='divisions'),
    path('districts/', DistrictsView.as_view(), name='districts'),
    path('thanas/', ThanasView.as_view(), name='thanas'),
    path('signup/', CustomerCreateView.as_view(), name='signup'),
    path('login/', CustomerRetrieveView.as_view(), name='login'),
    path('profile_update/', CustomerUpdateView.as_view(), name='profile_update'),
    path('password_update/', PasswordUpdateView.as_view(), name='password_update'),
    path('password_reset/', CustomerResetView.as_view(), name='password_reset'),
    path('username/', MobileNumberExistsView.as_view(), name='username'),
    path('password/', PasswordExistsView.as_view(), name='password'),
    path('myorder/<str:username>/', OrderRetrieveView.as_view(), name='myorder'),
    path('save_json_data/', views.save_json_data, name='save_json_data'),
    re_path(r'^favicon\.ico$', serve, {'path': 'static/favicon.ico'}),
    # re_path(r'^manage/media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),
]

if settings.DEBUG:
    # urlpatterns += static('/manage' + settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT, show_indexes=True)

# if settings.DEBUG:
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


