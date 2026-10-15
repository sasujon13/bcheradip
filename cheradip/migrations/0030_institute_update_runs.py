import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0029_institute_teacher')]

    operations = [
        migrations.CreateModel(
            name='InstituteUpdateRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('cursor', models.CharField(blank=True, default='', max_length=15)),
                ('total', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(default='running', max_length=16)),
                ('locked_until', models.DateTimeField(blank=True, null=True)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['-started_at']},
        ),
        migrations.CreateModel(
            name='InstituteUpdateAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eiin', models.CharField(max_length=15)),
                ('status', models.CharField(max_length=16)),
                ('outcome', models.CharField(blank=True, default='', max_length=32)),
                ('detail', models.CharField(blank=True, default='', max_length=255)),
                ('attempts', models.PositiveSmallIntegerField(default=1)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='cheradip.instituteupdaterun')),
            ],
            options={'ordering': ['eiin']},
        ),
        migrations.AddConstraint(
            model_name='instituteupdateattempt',
            constraint=models.UniqueConstraint(fields=('run', 'eiin'), name='unique_institute_update_attempt'),
        ),
    ]
