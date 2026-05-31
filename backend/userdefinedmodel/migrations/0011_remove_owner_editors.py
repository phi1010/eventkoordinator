from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('userdefinedmodel', '0010_add_transition_name_unique'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userdefinedmodelentity',
            name='editors',
        ),
        migrations.RemoveField(
            model_name='userdefinedmodelentity',
            name='owner',
        ),
    ]
