from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("userdefinedmodel", "0012_remove_workflowtransition_unique_transition_name_per_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="fieldedit",
            name="language",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
