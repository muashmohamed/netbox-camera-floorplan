# Hand-written (not auto-generated via makemigrations) — see the migration
# 0013/0014 docstrings for why. This migration performs only pure, safe
# same-type renames: connected_nvr -> connected_hub, nvr_channel ->
# hub_slot, and category -> category_legacy (all three unchanged field
# types), plus one ADDITIVE new field (category_fk, a deliberately
# temporary name) and a compatible int-to-int widening of
# channel_capacity. No existing data is dropped or reinterpreted by this
# migration — every operation here is either a rename or purely additive.

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_camera_floorplan', '0011_equipmentcategory'),
    ]

    operations = [
        # --- CameraPlacement: NVR-specific -> generic hub/slot naming ---
        # RemoveConstraint MUST come before the renames below: the
        # constraint's field list still names the OLD fields
        # (connected_nvr, nvr_channel) until it's removed — renaming
        # those fields first would leave the constraint referencing
        # fields that no longer exist, which breaks table
        # reconstruction (verified by simulating this migration:
        # reversing this order raises FieldDoesNotExist).
        migrations.RemoveConstraint(
            model_name='cameraplacement',
            name='unique_nvr_channel_assignment',
        ),
        migrations.RenameField(
            model_name='cameraplacement',
            old_name='connected_nvr',
            new_name='connected_hub',
        ),
        migrations.RenameField(
            model_name='cameraplacement',
            old_name='nvr_channel',
            new_name='hub_slot',
        ),
        migrations.AlterField(
            model_name='cameraplacement',
            name='connected_hub',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='connected_devices',
                to='netbox_camera_floorplan.cameraplacement',
                verbose_name='connected hub',
                help_text=(
                    "The hub device (Device Type category with \"is a hub\" enabled "
                    "— e.g. NVR, Access Control panel) this device connects into. "
                    "Only already-placed hubs can be selected — place the hub "
                    "itself first."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='cameraplacement',
            name='hub_slot',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                verbose_name='hub slot',
                help_text=(
                    "Slot/channel number on the connected hub (e.g. NVR channel, "
                    "Access Control door/reader slot) — labeled per that hub's own "
                    "Device Type category (e.g. \"D1\", \"Door 1\")."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name='cameraplacement',
            constraint=models.UniqueConstraint(
                condition=models.Q(('connected_hub__isnull', False)),
                fields=('connected_hub', 'hub_slot'),
                name='unique_hub_slot_assignment',
            ),
        ),

        # --- CameraType: preserve existing category strings under a ---
        # --- temporary name before the FK conversion (see 0013/0014) ---
        migrations.RenameField(
            model_name='cameratype',
            old_name='category',
            new_name='category_legacy',
        ),

        # --- CameraType: widen channel_capacity from a fixed-choice ---
        # --- field to a plain integer (safe: same underlying int data) ---
        migrations.AlterField(
            model_name='cameratype',
            name='channel_capacity',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name='channel/slot capacity',
                validators=[django.core.validators.MinValueValidator(1)],
                help_text=(
                    "Hub categories only (e.g. NVR, Access Control) — ignored for "
                    "every other category. The maximum number of devices this hub "
                    "can connect (e.g. a 32-channel NVR accepts up to 32 cameras; "
                    "a 4-door Access Control panel accepts up to 4 reader/button "
                    "devices). Enter the exact number for your actual hardware — "
                    "no preset list to run out of."
                ),
            ),
        ),

        # --- CameraType: additive category_fk (temporary name) ---
        # Deliberately NOT named "category" yet — see migration 0014 for
        # why the rename to the final name happens only after the old
        # CharField (still present under its original name at this
        # point) is fully retired by the data migration in 0013.
        migrations.AddField(
            model_name='cameratype',
            name='category_fk',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='camera_types',
                to='netbox_camera_floorplan.equipmentcategory',
            ),
        ),
    ]
