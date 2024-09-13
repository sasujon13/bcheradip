# Generated by Django 5.0.6 on 2024-09-13 09:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Board',
            fields=[
                ('board_code', models.CharField(max_length=3, primary_key=True, serialize=False, unique=True)),
                ('board_name', models.CharField(blank=True, max_length=31, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Year',
            fields=[
                ('year_code', models.CharField(max_length=5, primary_key=True, serialize=False, unique=True)),
                ('year_name', models.CharField(blank=True, max_length=9, unique=True)),
            ],
        ),
    ]
