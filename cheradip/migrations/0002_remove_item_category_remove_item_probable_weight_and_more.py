# Generated by Django 5.0.6 on 2024-07-22 08:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='item',
            name='category',
        ),
        migrations.RemoveField(
            model_name='item',
            name='probable_weight',
        ),
        migrations.RemoveField(
            model_name='item',
            name='variants',
        ),
        migrations.AlterField(
            model_name='item',
            name='code',
            field=models.CharField(max_length=4, null=True),
        ),
        migrations.AlterField(
            model_name='item',
            name='size',
            field=models.CharField(choices=[('nctb', 'nctb'), ('book', 'book'), ('guide', 'guide'), ('cheradip', 'cheradip')], max_length=14, null=True),
        ),
        migrations.AlterField(
            model_name='item',
            name='types',
            field=models.CharField(choices=[('science', 'science'), ('business', 'business'), ('humanities', 'hamanities'), ('compulsory', 'compulsory'), ('sac', 'sac'), ('ac', 'ac'), ('sc', 'sc')], default='Soft', max_length=15, null=True),
        ),
    ]