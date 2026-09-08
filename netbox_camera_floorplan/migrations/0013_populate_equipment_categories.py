# Hand-written data migration. This is the step that actually preserves
# every existing CameraType row's category assignment through the
# CharField -> ForeignKey conversion.
#
# Why hand-written: Django's makemigrations autodetector cannot safely
# generate this on its own. A straight CharField-to-ForeignKey change
# under the SAME field name gets treated as an AlterField (an attempted
# in-place column retype), which Postgres cannot do meaningfully for a
# text column becoming an integer FK reference — it would fail outright
# or require a manual USING clause with no principled default mapping.
# Splitting it into add-new-field (0012) -> copy-data (this file) ->
# drop-old-field (0014) avoids that entirely, at the cost of needing
# this migration to be written by hand instead of auto-generated.
#
# The 12 EquipmentCategory rows below exactly mirror the CATEGORY_CHOICES
# that used to be hardcoded on CameraType (now removed from the code
# entirely — categories are pure data from here on). If any of these
# already exist (e.g. created manually while testing the Phase 1
# EquipmentCategory admin pages before this migration ran), this
# migration does NOT overwrite their name/description, but DOES force
# is_camera/is_hub/slot_label_format to the values this app's logic
# depends on — an Access Control or NVR category that isn't correctly
# flagged is_hub would silently break hub/slot assignment everywhere.

from django.db import migrations

CATEGORY_DEFS = [
    # (slug, name, is_camera, is_hub, slot_label_format)
    ("camera", "Camera", True, False, "{n}"),
    ("ap", "Access Point", False, False, "{n}"),
    ("access_control", "Access Control", False, True, "Door {n}"),
    ("switch", "Switch", False, False, "{n}"),
    ("ups", "UPS", False, False, "{n}"),
    ("server", "Server", False, False, "{n}"),
    ("router", "Router", False, False, "{n}"),
    ("firewall", "Firewall", False, False, "{n}"),
    ("nvr", "NVR", False, True, "D{n}"),
    ("ont", "ONT", False, False, "{n}"),
    ("modem", "Modem", False, False, "{n}"),
    ("other", "Other", False, False, "{n}"),
]


def populate_categories_and_map(apps, schema_editor):
    EquipmentCategory = apps.get_model("netbox_camera_floorplan", "EquipmentCategory")
    CameraType = apps.get_model("netbox_camera_floorplan", "CameraType")

    slug_to_category = {}
    for slug, name, is_camera, is_hub, slot_label_format in CATEGORY_DEFS:
        category, created = EquipmentCategory.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "is_camera": is_camera,
                "is_hub": is_hub,
                "slot_label_format": slot_label_format,
            },
        )
        if not created:
            changed = False
            if category.is_camera != is_camera:
                category.is_camera = is_camera
                changed = True
            if category.is_hub != is_hub:
                category.is_hub = is_hub
                changed = True
            if is_hub and not category.slot_label_format:
                category.slot_label_format = slot_label_format
                changed = True
            if changed:
                category.save()
        slug_to_category[slug] = category

    fallback = slug_to_category["other"]
    for camera_type in CameraType.objects.all():
        legacy_value = camera_type.category_legacy or "camera"
        camera_type.category_fk = slug_to_category.get(legacy_value, fallback)
        camera_type.save(update_fields=["category_fk"])


def reverse_map_back_to_legacy(apps, schema_editor):
    """
    Best-effort reverse: writes each CameraType's category_fk slug back
    into category_legacy. Does not delete the EquipmentCategory rows
    created above (harmless to leave behind; may already be referenced
    elsewhere by the time anyone reverses this far).
    """
    CameraType = apps.get_model("netbox_camera_floorplan", "CameraType")
    for camera_type in CameraType.objects.select_related("category_fk").all():
        camera_type.category_legacy = (
            camera_type.category_fk.slug if camera_type.category_fk_id else "camera"
        )
        camera_type.save(update_fields=["category_legacy"])


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_camera_floorplan", "0012_hub_slot_rename_and_category_fk"),
    ]

    operations = [
        migrations.RunPython(populate_categories_and_map, reverse_map_back_to_legacy),
    ]
