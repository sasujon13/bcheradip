# Generated by Django 5.0.6 on 2024-07-22 18:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0006_remove_customer_type_customer_acctype'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='acctype',
            field=models.CharField(choices=[('teacher', 'teacher'), ('student', 'student')], default='teacher', max_length=7),
        ),
    ]
