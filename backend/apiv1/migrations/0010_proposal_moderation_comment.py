from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apiv1', '0009_remove_historicalproposal_is_regular_member_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalproposal',
            name='moderation_comment',
            field=models.TextField(blank=True, max_length=2000),
        ),
        migrations.AddField(
            model_name='proposal',
            name='moderation_comment',
            field=models.TextField(blank=True, max_length=2000),
        ),
        migrations.AlterModelOptions(
            name='proposal',
            options={
                'ordering': ['-created_at'],
                'permissions': [
                    ('browse_proposal', 'Can browse proposal list'),
                    ('accept_proposal', 'Can accept proposals (when the workflow allows it)'),
                    ('reject_proposal', 'Can reject proposals (when the workflow allows it)'),
                    ('submit_proposal', 'Can submit proposals (when the workflow allows it)'),
                    ('revise_proposal', 'Can request for revision of proposals (when the workflow allows it)'),
                    ('moderate_proposal', 'Can write moderation comments on proposals'),
                ],
            },
        ),
    ]
