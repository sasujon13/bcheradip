# Generated manually for AILT-aligned auth fields + OTP shape

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("childcare", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="parentaccount",
            name="email",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="parentaccount",
            name="username",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="parentaccount",
            name="password_hash",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="parentaccount",
            name="full_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="parentaccount",
            name="role",
            field=models.CharField(default="user", max_length=16),
        ),
        migrations.AddField(
            model_name="parentaccount",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="parentaccount",
            name="registered_device_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AlterField(
            model_name="parentaccount",
            name="mobile_number",
            field=models.CharField(blank=True, db_index=True, max_length=20, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="devicesession",
            name="token",
            field=models.CharField(blank=True, db_index=True, max_length=128, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="devicesession",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="devicesession",
            name="device_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.RemoveField(model_name="otpcode", name="mobile_number"),
        migrations.RemoveField(model_name="otpcode", name="purpose"),
        migrations.RemoveField(model_name="otpcode", name="consumed_at"),
        migrations.AddField(
            model_name="otpcode",
            name="target",
            field=models.CharField(db_index=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="otpcode",
            name="channel",
            field=models.CharField(default="email", max_length=32),
        ),
        migrations.AddField(
            model_name="otpcode",
            name="used",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="otpcode",
            name="code",
            field=models.CharField(max_length=8),
        ),
    ]
