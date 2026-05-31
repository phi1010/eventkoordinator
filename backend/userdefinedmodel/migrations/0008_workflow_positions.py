from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userdefinedmodel', '0007_alter_fielddefinition_data_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='workflowstate',
            name='position_x',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='workflowstate',
            name='position_y',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='workflowtransition',
            name='source_handle',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='workflowtransition',
            name='target_handle',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
    ]
