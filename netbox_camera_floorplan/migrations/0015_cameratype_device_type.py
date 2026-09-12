import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dcim', '0241_nullify_empty_cable_end'),
        ('netbox_camera_floorplan', '0014_finalize_category_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='cameratype',
            name='device_type',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='dcim.devicetype',
                verbose_name='NetBox Device Type',
                help_text=(
                    "Optional: link this to the real NetBox hardware type (manufacturer/model) "
                    "this entry represents. One-time setup per Device Type — once set, any "
                    "NetBox device using that hardware type automatically suggests this entry "
                    "when placing it (icon, category, capacity all apply without re-picking "
                    "them by hand). Leave blank if this entry doesn't correspond to one "
                    "specific real hardware model, or if several plugin types share the same "
                    "generic placeholder hardware type — matching stays ambiguous either way, "
                    "so nothing auto-selects until it's set."
                ),
            ),
        ),
    ]
