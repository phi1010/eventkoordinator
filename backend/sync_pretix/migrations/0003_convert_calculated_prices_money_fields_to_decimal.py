from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sync_pretix", "0002_calculatedprices_pricing_configuration_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="calculatedprices",
            name="guest_discounted_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="calculatedprices",
            name="guest_regular_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="calculatedprices",
            name="member_discounted_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="calculatedprices",
            name="member_regular_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="historicalcalculatedprices",
            name="guest_discounted_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="historicalcalculatedprices",
            name="guest_regular_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="historicalcalculatedprices",
            name="member_discounted_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="historicalcalculatedprices",
            name="member_regular_gross_eur",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
    ]

