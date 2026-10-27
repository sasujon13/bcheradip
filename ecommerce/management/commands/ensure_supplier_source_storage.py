"""Lossless expansion for the already-existing source table on legacy deployments."""
from django.core.management.base import BaseCommand
from django.db import connections,models
from ecommerce.models import SupplierSourceProduct


class Command(BaseCommand):
    def handle(self,*args,**options):
        connection=connections['ecommerce']
        if connection.vendor!='mysql':return
        table=SupplierSourceProduct._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute('SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s',[table,'sku'])
            row=cursor.fetchone()
        if not row:raise ValueError('Source SKU column is absent; run the normal schema existence check first.')
        if row[0]=='longtext':self.stdout.write('Original source SKU storage already supports complete values.');return
        old=models.CharField(max_length=500,blank=True);old.set_attributes_from_name('sku');old.model=SupplierSourceProduct
        with connection.schema_editor() as editor:
            editor.alter_field(SupplierSourceProduct,old,SupplierSourceProduct._meta.get_field('sku'),strict=False)
        self.stdout.write('Expanded original source SKU storage without truncating or replacing records.')
