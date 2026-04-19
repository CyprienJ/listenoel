import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from gifts.forms import GroupForm
from gifts.models import Group


@login_required
@require_POST
def create_group(request):
    form = GroupForm(request.POST)
    if form.is_valid():
        group = form.save(commit=False)
        group.created_by = request.user
        group.save()
        group.members.add(request.user)
        msg = _("Group '%(name)s' created ! Share this code: %(token)s") % {
            "name": group.name,
            "token": group.group_token,
        }
        messages.success(request, msg)
    else:
        for error in form.errors.values():
            messages.error(request, error.as_text())

    return redirect("dashboard")


@login_required
@require_GET
def join_group(request, token=None):

    if request.user in Group.objects.get(group_token=token).members.all():
        messages.info(
            request, _("You are already a member of the group '%s'.") % Group.objects.get(group_token=token).name
        )
        return redirect("dashboard")

    group = Group.objects.filter(group_token=token).first()
    if not group:
        return render(request, "groups/group_not_found.html", status=404)

    return render(request, "groups/group_preview.html", status=200, context={"group": group})


@login_required
@require_GET
def join_group_confirm(request, token):
    group = Group.objects.filter(group_token=token).first()

    if group:
        if request.user in group.members.all():
            messages.info(request, _("You are already a member of the group '%s'.") % group.name)
        else:
            group.members.add(request.user)
            messages.success(request, _("You have joined the group '%s'!") % group.name)
        return redirect("group_detail", group_id=group.id)
    else:
        messages.error(request, _("No group found with this code."))

    return redirect("dashboard")


@login_required
@require_GET
def group_detail(request, group_id):
    group = Group.objects.filter(id=group_id).first()

    if not group:
        return render(request, "groups/group_not_found.html", status=404)

    if request.user not in group.members.all():
        return HttpResponseForbidden(_("You are not a member of this group."))

    return render(request, "groups/group_detail.html", {"group": group})


@login_required
@require_POST
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user in group.members.all():
        group.members.remove(request.user)
        messages.success(request, _("You have left the group '%s'.") % group.name)
    if group.members.count() == 0:
        group.delete()
    return redirect("dashboard")


@login_required
@require_POST
def edit_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if request.user not in group.members.all():
        return redirect("dashboard")

    if request.method == "POST":
        new_name = request.POST.get("name")
        new_description = request.POST.get("description")
        new_image = request.FILES.get("image")

        if new_name:
            group.name = new_name

        if new_image:
            if group.image and os.path.isfile(group.image.path):
                os.remove(group.image.path)
            group.image = new_image

        group.description = new_description

        new_show_history = request.POST.get("show_history") == "on"
        if group.show_history and not new_show_history:
            from .models import Gift

            Gift.objects.filter(group_reserved_on=group, offered=True).delete()
        group.show_history = new_show_history
        group.show_balance = request.POST.get("show_balance") == "on"

        group.save()

        return redirect("group_detail", group_id=group.id)

    return redirect("group_detail", group_id=group.id)


@login_required
@require_POST
def regenerate_group_token(request, group_id):
    group = get_object_or_404(
        Group,
        id=group_id,
    )
    group.group_token = ""  # Will be regenerated in save()
    group.save()
    messages.success(request, _("New invitation code generated !"))
    return redirect("group_detail", group_id=group.id)
