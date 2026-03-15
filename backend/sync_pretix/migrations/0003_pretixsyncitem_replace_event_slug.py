import django.db.models.deletion
from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [
        ("sync_pretix", "0002_add_pretixsyncitem"),
    ]
    operations = [
        # ---- PretixSyncItem (real table) --------------------------------
        migrations.AddField(
            model_name="pretixsyncitem",
            name="area_association",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="sync_items",
                to="sync_pretix.pretixsynctargetareaassociation",
                verbose_name="Area Association",
                help_text="The area-to-event-slug mapping used when pushing to Pretix.",
            ),
        ),
        migrations.AddField(
            model_name="pretixsyncitem",
            name="subevent_slug",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="Pretix Subevent ID",
                help_text="ID of the Pretix subevent created for this event. Set on first push.",
            ),
        ),
        migrations.RemoveField(
            model_name="pretixsyncitem",
            name="event_slug",
        ),
        # ---- HistoricalPretixSyncItem -----------------------------------
        migrations.AddField(
            model_name="historicalpretixsyncitem",
            name="area_association",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="sync_pretix.pretixsynctargetareaassociation",
                verbose_name="Area Association",
            ),
        ),
        migrations.AddField(
            model_name="historicalpretixsyncitem",
            name="subevent_slug",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="Pretix Subevent ID",
                help_text="ID of the Pretix subevent created for this event. Set on first push.",
            ),
        ),
        migrations.RemoveField(
            model_name="historicalpretixsyncitem",
            name="event_slug",
        ),
    ]
