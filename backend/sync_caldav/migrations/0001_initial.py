import django.db.models.deletion
import simple_history.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('apiv1', '0002_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CalDAVSyncTarget',
            fields=[
                ('syncbasetarget_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='apiv1.syncbasetarget')),
                ('name', models.CharField(max_length=255)),
                ('url', models.URLField(max_length=2000)),
                ('username', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=255)),
                ('calendar_display_name', models.CharField(max_length=255)),
                ('instance_base_url', models.CharField(blank=True, default='', max_length=2000)),
            ],
            options={
                'abstract': False,
            },
            bases=('apiv1.syncbasetarget',),
        ),
        migrations.CreateModel(
            name='HistoricalCalDAVSyncTarget',
            fields=[
                ('syncbasetarget_ptr', models.ForeignKey(auto_created=True, blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, parent_link=True, related_name='+', to='apiv1.syncbasetarget')),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('url', models.URLField(db_index=True, max_length=2000)),
                ('username', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=255)),
                ('calendar_display_name', models.CharField(max_length=255)),
                ('instance_base_url', models.CharField(blank=True, default='', max_length=2000)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('polymorphic_ctype', models.ForeignKey(blank=True, db_constraint=False, editable=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'historical cal dav sync target',
                'verbose_name_plural': 'historical cal dav sync targets',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalCalDAVSyncItem',
            fields=[
                ('syncbaseitem_ptr', models.ForeignKey(auto_created=True, blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, parent_link=True, related_name='+', to='apiv1.syncbaseitem')),
                ('id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('flag_push', models.BooleanField(default=False)),
                ('caldav_uid', models.CharField(db_index=True, max_length=255)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('polymorphic_ctype', models.ForeignKey(blank=True, db_constraint=False, editable=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='contenttypes.contenttype')),
                ('related_event', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='apiv1.event')),
                ('sync_target', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='sync_caldav.caldavsynctarget')),
            ],
            options={
                'verbose_name': 'historical cal dav sync item',
                'verbose_name_plural': 'historical cal dav sync items',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='CalDAVSyncItem',
            fields=[
                ('syncbaseitem_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='apiv1.syncbaseitem')),
                ('caldav_uid', models.CharField(max_length=255, unique=True)),
                ('sync_target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='sync_caldav.caldavsynctarget')),
            ],
            options={
                'abstract': False,
            },
            bases=('apiv1.syncbaseitem',),
        ),
    ]
