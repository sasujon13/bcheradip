from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("childcare", "0002_ailt_aligned_auth"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearnerScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_points", models.IntegerField(db_index=True, default=0)),
                ("contest_week", models.CharField(blank=True, default="", max_length=32)),
                ("contest_score", models.IntegerField(default=0)),
                ("scores_json", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "child",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="learner_scores",
                        to="childcare.childprofile",
                    ),
                ),
                (
                    "parent",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learner_score",
                        to="childcare.parentaccount",
                    ),
                ),
            ],
            options={
                "verbose_name": "Learner score",
                "verbose_name_plural": "Learner scores",
                "db_table": "cc_learner_scores",
                "ordering": ["-total_points", "id"],
            },
        ),
    ]
