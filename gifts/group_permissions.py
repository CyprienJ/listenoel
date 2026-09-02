from django.http import HttpResponseForbidden
from django.utils.translation import gettext as _


def can_manage_group_invitations(user, group):
    """Single policy point ready for future owner/admin/member roles."""
    return bool(user.is_authenticated and group.members.filter(pk=user.pk).exists())


def group_invitation_forbidden_response():
    return HttpResponseForbidden(_("You do not have permission to manage invitations for this group."))
