from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from .context_processors import application_version


@override_settings(APP_VERSION="2.8.3", DEPLOYMENT_REVISION="a37bd82c41f9")
class ApplicationVersionTest(SimpleTestCase):
    def test_context_processor_exposes_version_and_revision(self):
        context = application_version(None)

        self.assertEqual(context["app_version"], "2.8.3")
        self.assertEqual(context["deployment_revision"], "a37bd82c41f9")
        self.assertEqual(context["deployment_revision_short"], "a37bd82")

    def test_footer_displays_version_and_privacy_link(self):
        response = self.client.get(reverse("welcome"))

        self.assertContains(response, "v2.8.3 (a37bd82)")
        self.assertContains(response, f'href="{reverse("privacy")}"', count=1)
