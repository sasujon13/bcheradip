from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .checkout_api import CheckoutProfileView, CheckoutQuoteView, StorePolicyView, DeliverySettingsView

from .views import (
    AdminBookAssetViewSet, AdminBookBuildJobViewSet, AdminBookViewSet,
    AdminCsvImportView, AdminDashboardView, AdminInventoryView, AdminOrderViewSet,
    AdminPaymentViewSet, AdminProductViewSet, BrandViewSet, CartView, CategoryViewSet,
    AccountHistoryView, BookViewSet, CheckoutView, DigitalBookDownloadView, DigitalLibraryView, NotificationView, OrderTrackingView, OrderViewSet, PaymentCreateView, ProductViewSet,
    ReviewCreateView, PublicBookAssetView, CartSummaryView, sample_csv,
)
from .management_api import (
    BrandManageViewSet, CategoryManageViewSet, CouponManageViewSet, ImportManageViewSet,
    ManagedOrderViewSet, ManagedPaymentViewSet, ManagedProductViewSet, ManagementAccessView,
    NotificationManageViewSet, ProductImageUploadView, ReviewManageViewSet, ShipmentManageViewSet, VariantManageViewSet, PricingPreviewView,
)

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='ecommerce-category')
router.register('brands', BrandViewSet, basename='ecommerce-brand')
router.register('products', ProductViewSet, basename='ecommerce-product')
router.register('books', BookViewSet, basename='ecommerce-book')
router.register('orders', OrderViewSet, basename='ecommerce-order')

admin_router = DefaultRouter()
admin_router.register('products', ManagedProductViewSet, basename='ecommerce-admin-product')
admin_router.register('categories', CategoryManageViewSet, basename='ecommerce-admin-category')
admin_router.register('variants', VariantManageViewSet, basename='ecommerce-admin-variant')
admin_router.register('brands', BrandManageViewSet, basename='ecommerce-admin-brand')
admin_router.register('coupons', CouponManageViewSet, basename='ecommerce-admin-coupon')
admin_router.register('shipments', ShipmentManageViewSet, basename='ecommerce-admin-shipment')
admin_router.register('reviews', ReviewManageViewSet, basename='ecommerce-admin-review')
admin_router.register('imports', ImportManageViewSet, basename='ecommerce-admin-import-history')
admin_router.register('notifications', NotificationManageViewSet, basename='ecommerce-admin-notification')
admin_router.register('books', AdminBookViewSet, basename='ecommerce-admin-book')
admin_router.register('book-assets', AdminBookAssetViewSet, basename='ecommerce-admin-book-asset')
admin_router.register('book-builds', AdminBookBuildJobViewSet, basename='ecommerce-admin-book-build')
admin_router.register('orders', ManagedOrderViewSet, basename='ecommerce-admin-order')
admin_router.register('payments', ManagedPaymentViewSet, basename='ecommerce-admin-payment')

urlpatterns = [
    path('admin/pricing/preview/', PricingPreviewView.as_view()),
    path('store-policy/', StorePolicyView.as_view()),
    path('checkout/profile/', CheckoutProfileView.as_view()),
    path('checkout/quote/', CheckoutQuoteView.as_view()),
    path('admin/delivery-settings/', DeliverySettingsView.as_view()),
    path('', include(router.urls)),
    path('cart/', CartView.as_view(), name='ecommerce-cart-new'),
    path('cart/summary/', CartSummaryView.as_view(), name='ecommerce-cart-summary'),
    path('cart/<str:token>/', CartView.as_view(), name='ecommerce-cart'),
    path('checkout/', CheckoutView.as_view(), name='ecommerce-checkout'),
    path('account/history/', AccountHistoryView.as_view(), name='ecommerce-account-history'),
    path('track/<str:order_number>/', OrderTrackingView.as_view(), name='ecommerce-order-tracking'),
    path('digital-library/', DigitalLibraryView.as_view(), name='ecommerce-digital-library'),
    path('book-assets/<int:pk>/download/', PublicBookAssetView.as_view(), name='ecommerce-public-book-asset'),
    path('digital-library/<slug:slug>/download/', DigitalBookDownloadView.as_view(), name='ecommerce-digital-book-download'),
    path('orders/<str:order_number>/payments/', PaymentCreateView.as_view(), name='ecommerce-payment-create'),
    path('products/<int:product_id>/reviews/', ReviewCreateView.as_view(), name='ecommerce-review-create'),
    path('notifications/', NotificationView.as_view(), name='ecommerce-notifications'),
    path('admin/access/', ManagementAccessView.as_view(), name='ecommerce-admin-access'),
    path('admin/upload-image/', ProductImageUploadView.as_view(), name='ecommerce-admin-upload-image'),
    path('admin/dashboard/', AdminDashboardView.as_view(), name='ecommerce-admin-dashboard'),
    path('admin/inventory/', AdminInventoryView.as_view(), name='ecommerce-admin-inventory'),
    path('admin/import/products/', AdminCsvImportView.as_view(), name='ecommerce-admin-import'),
    path('admin/import/sample.csv', sample_csv, name='ecommerce-sample-csv'),
    path('admin/', include(admin_router.urls)),
]

