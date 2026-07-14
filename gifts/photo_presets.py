from pathlib import Path

from django.contrib.staticfiles import finders
from django.templatetags.static import static

IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
PRESET_DIRS = {
    "profile": "gifts/presets/profile",
    "group": "gifts/presets/group",
}


def list_photo_presets(kind):
    preset_dir = PRESET_DIRS[kind]
    prefix = f"{preset_dir}/"
    presets = {}

    for finder in finders.get_finders():
        for path, _storage in finder.list([]):
            if not path.startswith(prefix):
                continue
            if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            presets[path] = {
                "path": path,
                "url": static(path),
                "name": Path(path).stem.replace("-", " ").replace("_", " "),
            }

    return [presets[path] for path in sorted(presets)]


def is_valid_photo_preset(kind, path):
    return path in {preset["path"] for preset in list_photo_presets(kind)}
