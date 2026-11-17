from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Comment, ServiceRequest, WorkOrder

COMPLETED = {ServiceRequest.Status.RESOLVED, ServiceRequest.Status.CLOSED}


@transaction.atomic
def service_request_create(*, requester, category, title, description, location, priority):
    item = ServiceRequest(
        requester=requester, category=category, title=title,
        description=description, location=location, priority=priority,
    )
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def service_request_update(*, item, actor, category, title, description, location, priority):
    locked = ServiceRequest.objects.select_for_update().get(id=item.id)
    if actor.pk != locked.requester_id and not actor.is_staff:
        raise PermissionDenied("You cannot edit this request.")
    if locked.status != ServiceRequest.Status.OPEN and not actor.is_staff:
        raise ValidationError("Only an open request can be edited.")
    locked.category, locked.title = category, title
    locked.description, locked.location, locked.priority = description, location, priority
    locked.full_clean()
    locked.save(update_fields=[
        "category", "title", "description", "location", "priority", "updated_at"
    ])
    return locked


@transaction.atomic
def comment_create(*, item, author, body):
    comment = Comment(service_request=item, author=author, body=body)
    comment.full_clean()
    comment.save()
    return comment


@transaction.atomic
def service_request_assign(*, item, technician, actor):
    if not actor.is_staff:
        raise PermissionDenied("Staff access is required.")
    if not (technician.is_staff and technician.is_active):
        raise ValidationError("The technician must be an active staff user.")
    locked = ServiceRequest.objects.select_for_update().get(id=item.id)
    if locked.status in COMPLETED:
        raise ValidationError("A completed request cannot be assigned.")
    work_order, _ = WorkOrder.objects.update_or_create(
        service_request=locked, defaults={"technician": technician}
    )
    locked.status = ServiceRequest.Status.ASSIGNED
    locked.full_clean()
    locked.save(update_fields=["status", "updated_at"])
    return work_order


@transaction.atomic
def service_request_resolve(*, item, actor, work_notes):
    locked = ServiceRequest.objects.select_for_update().get(id=item.id)
    try:
        work_order = WorkOrder.objects.select_for_update().get(service_request=locked)
    except WorkOrder.DoesNotExist as exc:
        raise ValidationError("Assign a technician before resolving.") from exc
    if actor.pk != work_order.technician_id and not actor.is_staff:
        raise PermissionDenied("Only the assigned technician or staff may resolve.")
    if locked.status in COMPLETED:
        raise ValidationError("This request is already completed.")
    notes = (work_notes or "").strip()
    if not notes:
        raise ValidationError("Work notes are required to resolve a request.")

    now = timezone.now()
    work_order.work_notes = notes
    work_order.completed_at = now
    work_order.full_clean()
    work_order.save(update_fields=["work_notes", "completed_at"])

    locked.status = ServiceRequest.Status.RESOLVED
    locked.resolved_at = now
    # The Lab 3 domain rule requires a resolution summary on resolved requests.
    locked.resolution_summary = notes
    locked.full_clean()
    locked.save(update_fields=["status", "resolved_at", "resolution_summary", "updated_at"])
    return locked
