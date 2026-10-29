from django.apps import AppConfig


class EcommerceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ecommerce'
    verbose_name = 'eCommerce'

    def ready(self):
        from .storefront_index import connect_signals
        from .storefront_taxonomy import connect_taxonomy_signals
        connect_signals()
        connect_taxonomy_signals()

