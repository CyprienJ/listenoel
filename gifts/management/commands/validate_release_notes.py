from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from gifts.release_notes import ReleaseNoteError, load_release_notes, parse_version


class Command(BaseCommand):
    help = "Validate the TOML release notes against the application version."

    def handle(self, *args, **options):
        try:
            current_version = parse_version(settings.APP_VERSION)
            notes = load_release_notes()
            future_notes = [note.version for note in notes if note.version_key > current_version]
        except ReleaseNoteError as exc:
            raise CommandError(str(exc)) from exc

        if future_notes:
            raise CommandError(
                f"Release notes newer than application version {settings.APP_VERSION}: {', '.join(future_notes)}"
            )
        self.stdout.write(self.style.SUCCESS(f"Validated {len(notes)} release note(s)."))
