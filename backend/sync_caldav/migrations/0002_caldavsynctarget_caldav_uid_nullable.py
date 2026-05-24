from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync_caldav', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='caldavsyncitem',
            name='caldav_uid',
            field=models.CharField(blank=True, default=None, max_length=255, null=True, unique=True),
        ),
    ]
