import re
import threading
import time
import uuid
from collections import defaultdict, deque
from urllib.parse import urlparse

import requests
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

MAX_REPORTS_PER_WINDOW = 3
RATE_LIMIT_WINDOW_SECONDS = 10 * 60
ALLOWED_DEVICE_TYPES = {"desktop", "mobile", "tablet", "unknown"}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
GITHUB_ISSUE_NUMBER = re.compile(r"^[1-9]\d*$", re.ASCII)


class BugReportForm(forms.Form):
    CATEGORY_CHOICES = (
        ("display", _("Display")),
        ("navigation", _("Navigation")),
        ("account", _("Account")),
        ("content", _("Content")),
        ("performance", _("Performance")),
        ("other", _("Other")),
    )
    FREQUENCY_CHOICES = (
        ("", _("Not specified")),
        ("always", _("Every time")),
        ("sometimes", _("Sometimes")),
        ("once", _("Only once")),
    )

    title = forms.CharField(max_length=120, label=_("Short title"))
    category = forms.ChoiceField(choices=CATEGORY_CHOICES, label=_("Category"))
    description = forms.CharField(max_length=2000, widget=forms.Textarea, label=_("Description"))
    reproduction_steps = forms.CharField(
        max_length=3000,
        widget=forms.Textarea,
        label=_("Steps to reproduce"),
        help_text=_("Describe the actions in order, one step per line."),
    )
    expected_result = forms.CharField(max_length=1500, widget=forms.Textarea, label=_("Expected result"))
    actual_result = forms.CharField(max_length=1500, widget=forms.Textarea, label=_("Actual result"))
    frequency = forms.ChoiceField(choices=FREQUENCY_CHOICES, required=False, label=_("Frequency"))
    public_consent = forms.BooleanField(
        label=_("I have checked that my report contains no personal or confidential information."),
    )

    page_path = forms.CharField(required=False, max_length=500, widget=forms.HiddenInput)
    browser = forms.CharField(required=False, max_length=150, widget=forms.HiddenInput)
    operating_system = forms.CharField(required=False, max_length=100, widget=forms.HiddenInput)
    device_type = forms.CharField(required=False, max_length=20, widget=forms.HiddenInput)
    viewport = forms.CharField(required=False, max_length=30, widget=forms.HiddenInput)
    browser_language = forms.CharField(required=False, max_length=35, widget=forms.HiddenInput)
    browser_timezone = forms.CharField(required=False, max_length=100, widget=forms.HiddenInput)
    website = forms.CharField(
        required=False,
        max_length=200,
        label="Website",
        widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        common_class = "form-control rounded-4 border-1"
        for field in self.fields.values():
            if field.widget.is_hidden:
                continue
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select rounded-4 border-1"
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            else:
                field.widget.attrs["class"] = common_class

        self.fields["title"].widget.attrs["placeholder"] = _("Example: the Save button does nothing")
        self.fields["description"].widget.attrs.update({"rows": 4})
        self.fields["reproduction_steps"].widget.attrs.update({"rows": 5})
        self.fields["expected_result"].widget.attrs.update({"rows": 3})
        self.fields["actual_result"].widget.attrs.update({"rows": 3})

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise ValidationError(_("The report could not be submitted."))
        return ""

    def clean_page_path(self):
        value = self.cleaned_data.get("page_path", "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
        if not path.startswith("/"):
            return ""
        return path[:500]

    def clean_device_type(self):
        value = self.cleaned_data.get("device_type", "unknown")
        return value if value in ALLOWED_DEVICE_TYPES else "unknown"


class _InMemoryRateLimiter:
    """Best-effort, process-local throttling without persistent report storage."""

    def __init__(self):
        self._attempts = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        threshold = now - RATE_LIMIT_WINDOW_SECONDS
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] < threshold:
                attempts.popleft()
            if len(attempts) >= MAX_REPORTS_PER_WINDOW:
                return False
            attempts.append(now)
            return True

    def clear(self):
        with self._lock:
            self._attempts.clear()


_rate_limiter = _InMemoryRateLimiter()


def _client_key(request):
    # Nginx overwrites X-Real-IP, unlike the client-controlled beginning of X-Forwarded-For.
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "unknown")


def _safe_text(value):
    """Remove control characters, HTML and active GitHub mentions from public text."""
    clean = strip_tags(value).strip()
    clean = CONTROL_CHARACTERS.sub("", clean)
    return clean.replace("@", "@\u200b")


def _public_route(path):
    if not path:
        return _("Unknown")
    try:
        match = resolve(path)
    except Resolver404:
        return _("Unknown page")
    # Django's route pattern contains placeholders instead of real invitation/event tokens.
    return f"/{match.route}"


def _numbered_steps(value):
    lines = [line.strip().lstrip("-•* ").strip() for line in value.splitlines() if line.strip()]
    return "\n".join(f"{index}. {_safe_text(line)}" for index, line in enumerate(lines, start=1))


def _issue_body(form, reference):
    data = form.cleaned_data
    frequency = dict(BugReportForm.FREQUENCY_CHOICES).get(data["frequency"], _("Not specified"))
    device_type = {
        "desktop": _("Desktop computer"),
        "mobile": _("Mobile"),
        "tablet": _("Tablet"),
        "unknown": _("Unknown"),
    }.get(data["device_type"], _("Unknown"))
    reported_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    route = _public_route(data["page_path"])

    return "\n".join(
        [
            f"## {_('Description')}",
            "",
            _safe_text(data["description"]),
            "",
            f"## {_('Steps to reproduce')}",
            "",
            _numbered_steps(data["reproduction_steps"]),
            "",
            f"## {_('Expected result')}",
            "",
            _safe_text(data["expected_result"]),
            "",
            f"## {_('Actual result')}",
            "",
            _safe_text(data["actual_result"]),
            "",
            f"## {_('Frequency')}",
            "",
            str(frequency),
            "",
            f"## {_('Technical context')}",
            "",
            f"- {_('Report reference')}: `{reference}`",
            f"- {_('Page route')}: `{route}`",
            f"- {_('Reported at')}: `{reported_at}`",
            f"- {_('Browser')}: `{_safe_text(data['browser']) or _('Unknown')}`",
            f"- {_('Operating system')}: `{_safe_text(data['operating_system']) or _('Unknown')}`",
            f"- {_('Device')}: `{device_type}`",
            f"- {_('Window')}: `{_safe_text(data['viewport']) or _('Unknown')}`",
            f"- {_('Language')}: `{_safe_text(data['browser_language']) or _('Unknown')}`",
            f"- {_('Time zone')}: `{_safe_text(data['browser_timezone']) or _('Unknown')}`",
            f"- {_('Application version')}: `{settings.APP_VERSION}`",
            f"- {_('Deployment revision')}: `{settings.DEPLOYMENT_REVISION or _('Unknown')}`",
            "",
            "---",
            str(_("Submitted from the public bug report form. Dynamic URL identifiers are intentionally hidden.")),
        ]
    )


def _create_github_issue(form):
    repository = settings.BUG_REPORT_REPOSITORY
    token = settings.BUG_REPORT_TOKEN
    if not repository or not token or repository.count("/") != 1:
        raise RuntimeError("GitHub bug reporting is not configured")

    reference = f"REPORT-{uuid.uuid4().hex[:12].upper()}"
    category = dict(BugReportForm.CATEGORY_CHOICES)[form.cleaned_data["category"]]
    title = f"[Bug][{category}] {_safe_text(form.cleaned_data['title'])}"
    payload = {
        "title": title[:256],
        "body": _issue_body(form, reference),
        "labels": settings.BUG_REPORT_LABELS,
    }
    response = requests.post(
        f"{settings.GITHUB_API_URL.rstrip('/')}/repos/{repository}/issues",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
            "User-Agent": "noscadeaux-bug-reporter",
        },
        json=payload,
        timeout=settings.BUG_REPORT_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    number = result.get("number")
    html_url = result.get("html_url", "")
    expected_prefix = f"https://github.com/{repository}/issues/"
    if not isinstance(number, int) or not html_url.startswith(expected_prefix):
        raise RuntimeError("GitHub returned an invalid issue response")
    return number


@require_http_methods(["GET", "POST"])
def bug_report(request: HttpRequest) -> HttpResponse:
    form = BugReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not _rate_limiter.allow(_client_key(request)):
            form.add_error(None, _("Too many reports have been submitted. Please try again in a few minutes."))
        else:
            try:
                issue_number = _create_github_issue(form)
            except (requests.RequestException, RuntimeError, ValueError):
                form.add_error(
                    None,
                    _("GitHub could not create the ticket. Your text has been kept in the form; please try again."),
                )
            else:
                return redirect(f"{reverse('bug_report_success')}?issue={issue_number}")

    return render(
        request,
        "gifts/bug_report.html",
        {
            "form": form,
            "app_version": settings.APP_VERSION,
            "reporting_configured": bool(settings.BUG_REPORT_TOKEN and settings.BUG_REPORT_REPOSITORY),
        },
    )


@require_GET
def bug_report_success(request: HttpRequest) -> HttpResponse:
    issue_number = request.GET.get("issue", "")
    repository = settings.BUG_REPORT_REPOSITORY
    if not GITHUB_ISSUE_NUMBER.fullmatch(issue_number) or repository.count("/") != 1:
        raise Http404
    issue_url = f"https://github.com/{repository}/issues/{issue_number}"
    return render(
        request,
        "gifts/bug_report_success.html",
        {"issue_number": issue_number, "issue_url": issue_url},
    )
