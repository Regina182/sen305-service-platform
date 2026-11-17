from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import AssignmentForm, CommentForm, ResolutionForm, ServiceRequestForm
from .models import ServiceRequest, WorkOrder
from .selectors import (
    service_request_filter,
    service_request_get,
    service_request_status_counts,
)
from .services import (
    COMPLETED,
    comment_create,
    service_request_assign,
    service_request_create,
    service_request_resolve,
    service_request_update,
)


def _visible_request_or_404(user, request_id):
    """Unauthorized and missing IDs both give 404, so ownership is never disclosed."""
    try:
        return service_request_get(user=user, request_id=request_id)
    except ServiceRequest.DoesNotExist as exc:
        raise Http404("Service request not found.") from exc


@login_required
def request_list(request):
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    queryset = service_request_filter(user=request.user, status=status, query=query)
    page_obj = Paginator(queryset, 10).get_page(request.GET.get("page"))
    return render(request, "requests_app/request_list.html", {
        "page_obj": page_obj,
        "status_choices": ServiceRequest.Status.choices,
        "selected_status": status,
        "query": query,
        "counts": service_request_status_counts(user=request.user),
    })


@login_required
def request_detail(request, request_id):
    user = request.user
    item = _visible_request_or_404(user, request_id)
    work_order = (
        WorkOrder.objects.select_related("technician")
        .filter(service_request_id=item.id).first()
    )
    comments = item.comments.select_related("author").order_by("created_at")
    if not user.is_staff:
        comments = comments.filter(is_internal=False)

    completed = item.status in COMPLETED
    is_assigned_technician = bool(work_order and work_order.technician_id == user.pk)
    # These flags mirror the server-side rules in services.py (UI and server agree).
    can_edit = user.is_staff or (
        item.requester_id == user.pk and item.status == ServiceRequest.Status.OPEN
    )
    can_assign = user.is_staff and not completed
    can_resolve = (user.is_staff or is_assigned_technician) and not completed

    return render(request, "requests_app/request_detail.html", {
        "item": item,
        "work_order": work_order,
        "comments": comments,
        "comment_form": CommentForm(),
        "assign_form": AssignmentForm() if can_assign else None,
        "resolve_form": ResolutionForm() if can_resolve and work_order else None,
        "can_edit": can_edit,
        "can_assign": can_assign,
        "can_resolve": can_resolve,
    })


@login_required
def request_create(request):
    form = ServiceRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = service_request_create(requester=request.user, **form.cleaned_data)
        messages.success(request, "Service request created.")
        return redirect("requests:detail", request_id=item.id)
    return render(request, "requests_app/request_form.html", {"form": form, "mode": "Create"})


@login_required
def request_update(request, request_id):
    item = _visible_request_or_404(request.user, request_id)
    form = ServiceRequestForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        try:
            item = service_request_update(item=item, actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Service request updated.")
            return redirect("requests:detail", request_id=item.id)
    return render(request, "requests_app/request_form.html", {
        "form": form, "mode": "Update", "item": item
    })


@require_POST
@login_required
def comment_add(request, request_id):
    item = _visible_request_or_404(request.user, request_id)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment_create(item=item, author=request.user, **form.cleaned_data)
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Enter at least 3 characters.")
    return redirect("requests:detail", request_id=item.id)


@require_POST
@login_required
def request_assign(request, request_id):
    if not request.user.is_staff:
        raise PermissionDenied("Staff access is required.")
    item = _visible_request_or_404(request.user, request_id)
    form = AssignmentForm(request.POST)
    if form.is_valid():
        try:
            service_request_assign(
                item=item, technician=form.cleaned_data["technician"], actor=request.user
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Technician assigned.")
    else:
        messages.error(request, "Choose a valid active staff technician.")
    return redirect("requests:detail", request_id=item.id)


@require_POST
@login_required
def request_resolve(request, request_id):
    item = _visible_request_or_404(request.user, request_id)
    form = ResolutionForm(request.POST)
    if form.is_valid():
        try:
            # PermissionDenied from the service propagates and becomes HTTP 403.
            service_request_resolve(
                item=item, actor=request.user, work_notes=form.cleaned_data["work_notes"]
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Request resolved.")
    else:
        for error in form.errors.get("work_notes", []):
            messages.error(request, error)
    return redirect("requests:detail", request_id=item.id)
