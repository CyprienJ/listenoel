import re
import tomllib
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from django.conf import settings

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ReleaseNoteError(ValueError):
    pass


def parse_version(value):
    match = VERSION_PATTERN.fullmatch(value or "")
    if not match:
        raise ReleaseNoteError(f"Invalid release version: {value!r}")
    return tuple(int(part) for part in match.groups())


@dataclass(frozen=True)
class ReleaseNote:
    version: str
    released_on: date
    translations: dict

    @property
    def version_key(self):
        return parse_version(self.version)

    def localized(self, language_code):
        language = (language_code or "").split("-", maxsplit=1)[0]
        translation = self.translations.get(language) or self.translations.get("fr") or self.translations.get("en")
        if translation is None:
            translation = next(iter(self.translations.values()))
        return {
            "version": self.version,
            "date": self.released_on.isoformat(),
            "title": translation["title"],
            "content": translation["content"],
        }


def _read_release_note(path):
    try:
        with path.open("rb") as release_file:
            data = tomllib.load(release_file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseNoteError(f"Cannot read {path.name}: {exc}") from exc

    version = data.get("version")
    parse_version(version)
    if path.stem != version:
        raise ReleaseNoteError(f"{path.name}: filename and version field must match")

    released_on = data.get("date")
    if not isinstance(released_on, date):
        raise ReleaseNoteError(f"{path.name}: date must use the YYYY-MM-DD TOML date format")

    translations = {}
    for language, translation in data.items():
        if language in {"version", "date"}:
            continue
        if not isinstance(translation, dict):
            raise ReleaseNoteError(f"{path.name}: {language} must be a translation table")
        title = translation.get("title")
        content = translation.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip():
            raise ReleaseNoteError(f"{path.name}: {language} requires non-empty title and content strings")
        translations[language] = {"title": title.strip(), "content": content.strip()}

    if "fr" not in translations:
        raise ReleaseNoteError(f"{path.name}: a French translation is required")
    return ReleaseNote(version=version, released_on=released_on, translations=translations)


@cache
def _load_release_notes(directory):
    path = Path(directory)
    if not path.exists():
        return ()
    notes = tuple(_read_release_note(note_path) for note_path in path.glob("*.toml"))
    versions = [note.version for note in notes]
    if len(versions) != len(set(versions)):
        raise ReleaseNoteError("Release note versions must be unique")
    return tuple(sorted(notes, key=lambda note: note.version_key))


def load_release_notes():
    return _load_release_notes(str(settings.RELEASE_NOTES_DIR))


def localized_release_notes(language_code):
    return [note.localized(language_code) for note in load_release_notes()]


def localized_release_notes_between(previous_version, current_version, language_code):
    previous = parse_version(previous_version)
    current = parse_version(current_version)
    return [note.localized(language_code) for note in load_release_notes() if previous < note.version_key <= current]
