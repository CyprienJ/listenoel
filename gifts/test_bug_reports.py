from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .bug_reports import _rate_limiter

BUG_REPORT_SETTINGS = {
    "BUG_REPORT_REPOSITORY": "example/public-bugs",
    "BUG_REPORT_TOKEN": "test-token",
    "BUG_REPORT_LABELS": ["bug", "source:user-report", "status:unconfirmed"],
    "GITHUB_API_URL": "https://api.github.com",
    "GITHUB_API_VERSION": "2022-11-28",
    "BUG_REPORT_TIMEOUT": 10,
    "APP_VERSION": "2.8.3",
    "DEPLOYMENT_REVISION": "a37bd82",
}


@override_settings(**BUG_REPORT_SETTINGS)
class BugReportTest(SimpleTestCase):
    def setUp(self):
        _rate_limiter.clear()
        self.url = reverse("bug_report")
        self.valid_data = {
            "title": "Save button does nothing",
            "category": "account",
            "description": "The settings are not saved.",
            "reproduction_steps": "Open settings\nChange the name\nSelect Save",
            "expected_result": "The new name is saved.",
            "actual_result": "Nothing happens.",
            "frequency": "always",
            "public_consent": "on",
            "page_path": "/fr/event/secret-invitation-token/",
            "browser": "Firefox 141",
            "operating_system": "Linux",
            "device_type": "desktop",
            "viewport": "1536 × 864",
            "browser_language": "fr-FR",
            "browser_timezone": "Europe/Paris",
            "website": "",
        }

    def test_form_is_publicly_accessible(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="description"')
        self.assertContains(response, 'name="public_consent"')
        self.assertNotContains(response, 'type="file"')

    def test_bug_report_link_is_in_footer_and_not_navigation(self):
        response = self.client.get(self.url)
        document = BeautifulSoup(response.content, "html.parser")

        self.assertIsNotNone(document.select_one("footer #bugReportLink"))
        self.assertIsNone(document.select_one("nav #bugReportLink"))

    def test_form_labels_follow_request_language(self):
        with override("fr"):
            french_response = self.client.get(reverse("bug_report"))
        with override("en"):
            english_response = self.client.get(reverse("bug_report"))

        self.assertContains(french_response, "Affichage")
        self.assertContains(english_response, "Display")

    @patch("gifts.bug_reports.requests.post")
    def test_valid_report_creates_github_issue_and_redirects_to_tracking_page(self, post):
        github_response = Mock()
        github_response.raise_for_status.return_value = None
        github_response.json.return_value = {
            "number": 317,
            "html_url": "https://github.com/example/public-bugs/issues/317",
        }
        post.return_value = github_response

        response = self.client.post(self.url, self.valid_data)

        self.assertRedirects(response, f"{reverse('bug_report_success')}?issue=317", fetch_redirect_response=False)
        post.assert_called_once()
        call = post.call_args
        self.assertEqual(call.args[0], "https://api.github.com/repos/example/public-bugs/issues")
        self.assertEqual(call.kwargs["timeout"], 10)
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer test-token")
        payload = call.kwargs["json"]
        self.assertEqual(payload["labels"], BUG_REPORT_SETTINGS["BUG_REPORT_LABELS"])
        self.assertIn("Save button does nothing", payload["title"])
        self.assertIn("/fr/event/<str:token>/", payload["body"])
        self.assertNotIn("secret-invitation-token", payload["body"])
        self.assertIn("Firefox 141", payload["body"])
        self.assertIn("2.8.3", payload["body"])
        self.assertIn("a37bd82", payload["body"])
        self.assertIn("## Contexte technique", payload["body"])

    def test_success_page_links_to_created_issue(self):
        response = self.client.get(reverse("bug_report_success"), {"issue": "317"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://github.com/example/public-bugs/issues/317")

    def test_success_page_rejects_invalid_issue_number(self):
        response = self.client.get(reverse("bug_report_success"), {"issue": "../settings"})

        self.assertEqual(response.status_code, 404)

    def test_success_page_only_accepts_get(self):
        response = self.client.post(reverse("bug_report_success"), {"issue": "317"})

        self.assertEqual(response.status_code, 405)

    @patch("gifts.bug_reports.requests.post")
    def test_github_failure_keeps_form_content_and_shows_error(self, post):
        post.side_effect = requests.Timeout

        response = self.client.post(self.url, self.valid_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save button does nothing")
        self.assertContains(response, "GitHub")

    @patch("gifts.bug_reports.requests.post")
    def test_honeypot_rejects_automated_submission(self, post):
        data = {**self.valid_data, "website": "https://spam.example"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        post.assert_not_called()

    @override_settings(BUG_REPORT_TOKEN="")
    @patch("gifts.bug_reports.requests.post")
    def test_missing_configuration_prevents_creation(self, post):
        response = self.client.post(self.url, self.valid_data)

        self.assertEqual(response.status_code, 200)
        post.assert_not_called()

    @patch("gifts.bug_reports.requests.post")
    def test_user_mentions_are_neutralized(self, post):
        github_response = Mock()
        github_response.raise_for_status.return_value = None
        github_response.json.return_value = {
            "number": 318,
            "html_url": "https://github.com/example/public-bugs/issues/318",
        }
        post.return_value = github_response
        data = {**self.valid_data, "description": "Please notify @everyone"}

        self.client.post(self.url, data)

        body = post.call_args.kwargs["json"]["body"]
        self.assertNotIn("@everyone", body)
        self.assertIn("@\u200beveryone", body)
