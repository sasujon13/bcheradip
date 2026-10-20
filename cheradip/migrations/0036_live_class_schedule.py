from django.conf import settings
from django.core.validators import URLValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0035_institute_refresh_event')]
    operations = [migrations.CreateModel(
        name='LiveClass',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=255)),
            ('subject', models.CharField(blank=True, max_length=255)),
            ('level', models.CharField(blank=True, max_length=100)),
            ('topic', models.CharField(blank=True, max_length=255)),
            ('teacher_name', models.CharField(blank=True, max_length=150)),
            ('description', models.TextField(blank=True)),
            ('starts_at', models.DateTimeField(help_text='Enter Bangladesh time (Asia/Dhaka).')),
            ('ends_at', models.DateTimeField(help_text='Enter Bangladesh time (Asia/Dhaka).')),
            ('join_url', models.URLField(blank=True, max_length=1000, validators=[URLValidator(schemes=['http', 'https'])], help_text='A meeting or livestream joining link. Required before publishing.')),
            ('status', models.CharField(choices=[('scheduled', 'Scheduled'), ('live', 'Live'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='scheduled', max_length=12)),
            ('is_published', models.BooleanField(default=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scheduled_live_classes', to=settings.AUTH_USER_MODEL)),
        ],
        options={'db_table': 'cheradip_live_class', 'ordering': ('starts_at', 'id'), 'verbose_name_plural': 'Live classes'},
    )]
