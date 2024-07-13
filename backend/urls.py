from django.contrib import admin
from django.conf.urls.static import static
from django.urls import path, re_path
from django.conf import settings
from cheradip import views
from cheradip.views import (
    ItemListCreateView,
    # CartListCreateView
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
    # path('admin/', admin.site.urls),
    path('admin/', admin.site.urls),
    path('item/', ItemListCreateView.as_view(), name='item'),
    # path('cart/', CartListCreateView.as_view(), name='cart'),
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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# if settings.DEBUG:
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


