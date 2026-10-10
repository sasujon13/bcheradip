from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminBookAssetViewSet, AdminBookBuildJobViewSet, AdminBookViewSet,
    AdminCsvImportView, AdminDashboardView, AdminInventoryView, AdminOrderViewSet,
    AdminPaymentViewSet, AdminProductViewSet, BrandViewSet, CartView, CategoryViewSet,
    AccountHistoryView, BookViewSet, CheckoutView, DigitalBookDownloadView, DigitalLibraryView, NotificationView, OrderTrackingView, OrderViewSet, PaymentCreateView, ProductViewSet,
    ReviewCreateView, sample_csv,
)

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='ecommerce-category')
router.register('brands', BrandViewSet, basename='ecommerce-brand')
router.register('products', ProductViewSet, basename='ecommerce-product')
router.register('books', BookViewSet, basename='ecommerce-book')
router.register('orders', OrderViewSet, basename='ecommerce-order')

admin_router = DefaultRouter()
admin_router.register('products', AdminProductViewSet, basename='ecommerce-admin-product')
admin_router.register('books', AdminBookViewSet, basename='ecommerce-admin-book')
admin_router.register('book-assets', AdminBookAssetViewSet, basename='ecommerce-admin-book-asset')
admin_router.register('book-builds', AdminBookBuildJobViewSet, basename='ecommerce-admin-book-build')
admin_router.register('orders', AdminOrderViewSet, basename='ecommerce-admin-order')
admin_router.register('payments', AdminPaymentViewSet, basename='ecommerce-admin-payment')

urlpatterns = [
    path('', include(router.urls)),
    path('cart/', CartView.as_view(), name='ecommerce-cart-new'),
    path('cart/<str:token>/', CartView.as_view(), name='ecommerce-cart'),
    path('checkout/', CheckoutView.as_view(), name='ecommerce-checkout'),
    path('account/history/', AccountHistoryView.as_view(), name='ecommerce-account-history'),
    path('track/<str:order_number>/', OrderTrackingView.as_view(), name='ecommerce-order-tracking'),
    path('digital-library/', DigitalLibraryView.as_view(), name='ecommerce-digital-library'),
    path('digital-library/<slug:slug>/download/', DigitalBookDownloadView.as_view(), name='ecommerce-digital-book-download'),
    path('orders/<str:order_number>/payments/', PaymentCreateView.as_view(), name='ecommerce-payment-create'),
    path('products/<int:product_id>/reviews/', ReviewCreateView.as_view(), name='ecommerce-review-create'),
    path('notifications/', NotificationView.as_view(), name='ecommerce-notifications'),
    path('admin/dashboard/', AdminDashboardView.as_view(), name='ecommerce-admin-dashboard'),
    path('admin/inventory/', AdminInventoryView.as_view(), name='ecommerce-admin-inventory'),
    path('admin/import/products/', AdminCsvImportView.as_view(), name='ecommerce-admin-import'),
    path('admin/import/sample.csv', sample_csv, name='ecommerce-sample-csv'),
    path('admin/', include(admin_router.urls)),
]

