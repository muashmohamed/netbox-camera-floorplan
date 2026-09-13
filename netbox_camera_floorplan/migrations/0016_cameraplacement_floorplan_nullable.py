import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_camera_floorplan', '0015_cameratype_device_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cameraplacement',
            name='floorplan',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cameras',
                to='netbox_camera_floorplan.floorplan',
                help_text=(
                    "Left blank when this placement was auto-created for a device whose "
                    "Location has no matching FloorPlan yet — create one for that Site/"
                    "Location and this will need to be set (either automatically on the "
                    "next save, or manually)."
                ),
            ),
        ),
    ]
