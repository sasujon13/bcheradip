from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('cheradip.urls')),
    path('', include('cheradip.urls')),  # keep root for backward compatibility
]


