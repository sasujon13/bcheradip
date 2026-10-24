from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0020_resumable_research')]
    operations = [migrations.AddField(
        model_name='supplierevidence', name='match_confidence',
        field=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
            validators=[MinValueValidator(0), MaxValueValidator(100)],
            help_text='Assessed similarity percent, 0–100. Not a substitute for verified exact matching.'))]
