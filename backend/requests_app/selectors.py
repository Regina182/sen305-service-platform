from django.db.models import Count, Q

from .models import ServiceRequest


def _visible(user):
    """Row-level visibility: staff see everything, others only their own requests."""
    queryset = ServiceRequest.objects.all()
    return queryset if user.is_staff else queryset.filter(requester=user)


def service_request_list(*, user):
    # Non-staff users must not learn how many internal comments exist.
    comment_filter = None if user.is_staff else Q(comments__is_internal=False)
    queryset = (
        ServiceRequest.objects
        .select_related("requester", "category")
        .annotate(comment_count=Count("comments", filter=comment_filter))
        .order_by("-created_at", "id")
    )
    return queryset if user.is_staff else queryset.filter(requester=user)


def service_request_filter(*, user, status="", query=""):
    queryset = service_request_list(user=user)
    if status:
        queryset = queryset.filter(status=status)
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
        )
    return queryset


def service_request_get(*, user, request_id):
    return service_request_list(user=user).get(id=request_id)


def service_request_status_counts(*, user):
    """One aggregate query over the requests this user may see (no comment join)."""
    Status = ServiceRequest.Status
    return _visible(user).aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Status.OPEN)),
        assigned=Count("id", filter=Q(status=Status.ASSIGNED)),
        resolved=Count("id", filter=Q(status=Status.RESOLVED)),
    )
