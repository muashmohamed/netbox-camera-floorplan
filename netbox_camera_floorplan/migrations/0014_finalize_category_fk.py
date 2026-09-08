# Hand-written, final step of the category CharField -> ForeignKey
# conversion started in 0012/0013. By this point every CameraType row's
# category_fk has already been populated by migration 0013's data copy,
# so category_legacy's string values are no longer needed and can be
# safely dropped. Renaming category_fk -> category is safe here (and
# only here) because the name "category" was freed up by 0012's earlier
# rename to category_legacy — nothing else claims that name at this
# point in the migration history.
#
# IMPORTANT: do not run this migration until you've confirmed 0013's
# data copy landed correctly (e.g. spot-check a few CameraType rows'
# category_fk against their original category via the Django shell or
# the admin). This migration is the point of no return for the old
# string values — reversing it only restores them via 0013's best-effort
# reverse function, which reconstructs from category_fk's slug, not the
# original raw string (harmless in practice since the mapping is 1:1,
# but worth knowing before running this forward).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_camera_floorplan', '0013_populate_equipment_categories'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cameratype',
            name='category_legacy',
        ),
        migrations.RenameField(
            model_name='cameratype',
            old_name='category_fk',
            new_name='category',
        ),
        # State-only cleanup: matches this field's final definition in
        # models.py exactly (blank=False — required in forms even though
        # null=True at the DB level — plus the real help_text), so a
        # future unrelated makemigrations run won't surprise you with an
        # unexpected AlterField on this column.
        migrations.AlterField(
            model_name='cameratype',
            name='category',
            field=models.ForeignKey(
                blank=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='camera_types',
                to='netbox_camera_floorplan.equipmentcategory',
                help_text=(
                    "Determines which fields apply — Direction and Field of View "
                    "(the coverage cone) are Camera-only, and channel/slot capacity "
                    "is Hub-only (NVR, Access Control) — hidden otherwise, since "
                    "they don't apply to an AP, switch, or UPS."
                ),
            ),
        ),
    ]
