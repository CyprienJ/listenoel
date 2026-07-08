from django.contrib.syndication.views import Feed
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import Gift, Group, Subscription


class SubscriptionFeed(Feed):
    """Private RSS feed for one subscriber/list-owner pair."""

    def get_object(self, request, feed_token):
        subscription = get_object_or_404(
            Subscription.objects.select_related("subscriber", "owner"),
            feed_token=feed_token,
            rss_enabled=True,
        )
        if not Group.objects.filter(members=subscription.subscriber).filter(members=subscription.owner).exists():
            # Group access may have been revoked after the feed URL was issued.
            raise Http404
        return subscription

    def title(self, subscription):
        return _("Gift list of %(name)s") % {"name": subscription.owner.nickname}

    def link(self, subscription):
        return reverse("view_list", args=[subscription.owner_id])

    def description(self, subscription):
        return _("New wishes and surprises added to %(name)s's list") % {"name": subscription.owner.nickname}

    def items(self, subscription):
        return (
            Gift.objects.filter(owner=subscription.owner, offered=False, event_list__isnull=True)
            .filter(Q(visible_in__isnull=True) | Q(visible_in__members=subscription.subscriber))
            .distinct()
            .order_by("-created_at")[:50]
        )

    def item_title(self, gift):
        return gift.title

    def item_description(self, gift):
        return gift.description

    def item_link(self, gift):
        return reverse("view_list", args=[gift.owner_id])

    def item_pubdate(self, gift):
        return gift.created_at

    def item_guid(self, gift):
        return f"gift-{gift.pk}"
