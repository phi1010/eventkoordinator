from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userdefinedmodel', '0009_remove_allows_edit_and_rules'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='workflowtransition',
            constraint=models.UniqueConstraint(
                fields=['workflow', 'name'],
                name='unique_transition_name_per_workflow',
            ),
        ),
    ]
