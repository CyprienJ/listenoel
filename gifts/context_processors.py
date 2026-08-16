from django.conf import settings


def application_version(_request):
    revision = settings.DEPLOYMENT_REVISION
    return {
        "app_version": settings.APP_VERSION,
        "deployment_revision": revision,
        "deployment_revision_short": revision[:7],
    }
