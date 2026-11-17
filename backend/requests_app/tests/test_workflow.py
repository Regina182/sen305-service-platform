import html
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.urls import reverse

from requests_app.forms import AssignmentForm
from requests_app.models import Category, ServiceRequest, WorkOrder
from requests_app.services import service_request_assign, service_request_resolve


class WorkflowBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="pass12345")
        self.other = User.objects.create_user("other", password="pass12345")
        self.staff = User.objects.create_user("staff", password="pass12345", is_staff=True)
        self.tech = User.objects.create_user("tech", password="pass12345", is_staff=True)
        self.category = Category.objects.create(name="ICT Support")
        self.item = self.make_request(title="Laboratory computer cannot start")

    def make_request(self, **overrides):
        values = {
            "requester": self.owner, "category": self.category,
            "title": "Laboratory computer cannot start",
            "description": "No power indicator.", "location": "Software Laboratory", "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest.objects.create(**values)

    def assign_url(self):
        return reverse("requests:assign", args=[self.item.id])

    def resolve_url(self):
        return reverse("requests:resolve", args=[self.item.id])


class AssignmentTests(WorkflowBase):
    def test_non_staff_assignment_returns_403_and_creates_no_work_order(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.assign_url(), {"technician": self.tech.id})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "open")

    def test_staff_assignment_creates_one_work_order_and_sets_assigned(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.assign_url(), {"technician": self.tech.id})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkOrder.objects.filter(service_request=self.item).count(), 1)
        self.assertEqual(WorkOrder.objects.get(service_request=self.item).technician, self.tech)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ServiceRequest.Status.ASSIGNED)

    def test_reassignment_keeps_a_single_work_order(self):
        self.client.force_login(self.staff)
        self.client.post(self.assign_url(), {"technician": self.tech.id})
        self.client.post(self.assign_url(), {"technician": self.staff.id})
        self.assertEqual(WorkOrder.objects.filter(service_request=self.item).count(), 1)
        self.assertEqual(WorkOrder.objects.get(service_request=self.item).technician, self.staff)

    def test_assignment_endpoint_requires_post(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.assign_url()).status_code, 405)

    def test_assignment_form_lists_only_active_staff(self):
        User = get_user_model()
        User.objects.create_user("inactive_staff", is_staff=True, is_active=False)
        names = set(AssignmentForm().fields["technician"].queryset.values_list("username", flat=True))
        self.assertEqual(names, {"staff", "tech"})

    def test_non_staff_technician_is_rejected(self):
        self.client.force_login(self.staff)
        self.client.post(self.assign_url(), {"technician": self.other.id})
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_assignment_form_hidden_from_non_staff(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertNotContains(response, self.assign_url())
        self.client.force_login(self.staff)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertContains(response, self.assign_url())

    def test_resolved_request_cannot_be_assigned(self):
        ServiceRequest.objects.filter(id=self.item.id).update(status="resolved")
        self.client.force_login(self.staff)
        self.client.post(self.assign_url(), {"technician": self.tech.id})
        self.assertEqual(WorkOrder.objects.count(), 0)


class ResolutionTests(WorkflowBase):
    def test_resolution_without_assignment_leaves_request_unchanged(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.resolve_url(), {"work_notes": "Replaced PSU"})
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "open")
        self.assertIsNone(self.item.resolved_at)

    def test_assigned_technician_resolution_changes_both_models(self):
        service_request_assign(item=self.item, technician=self.tech, actor=self.staff)
        self.client.force_login(self.tech)
        response = self.client.post(self.resolve_url(), {"work_notes": "Replaced the power supply"})
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        work_order = WorkOrder.objects.get(service_request=self.item)
        self.assertEqual(self.item.status, ServiceRequest.Status.RESOLVED)
        self.assertIsNotNone(self.item.resolved_at)
        self.assertEqual(self.item.resolution_summary, "Replaced the power supply")
        self.assertEqual(work_order.work_notes, "Replaced the power supply")
        self.assertIsNotNone(work_order.completed_at)

    def test_requester_who_is_not_assigned_gets_403(self):
        service_request_assign(item=self.item, technician=self.tech, actor=self.staff)
        self.client.force_login(self.owner)
        response = self.client.post(self.resolve_url(), {"work_notes": "I fixed it myself"})
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "assigned")

    def test_other_requester_gets_404_on_resolve(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.resolve_url(), {"work_notes": "x" * 5}).status_code, 404)

    def test_blank_work_notes_do_not_resolve(self):
        service_request_assign(item=self.item, technician=self.tech, actor=self.staff)
        self.client.force_login(self.tech)
        self.client.post(self.resolve_url(), {"work_notes": "   "})
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "assigned")

    def test_resolution_form_visibility(self):
        service_request_assign(item=self.item, technician=self.tech, actor=self.staff)
        detail = reverse("requests:detail", args=[self.item.id])
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(detail), self.resolve_url())
        self.client.force_login(self.tech)
        self.assertContains(self.client.get(detail), self.resolve_url())


class AtomicityTests(WorkflowBase):
    def test_assignment_rolls_back_when_status_write_fails(self):
        with patch.object(ServiceRequest, "save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                service_request_assign(item=self.item, technician=self.tech, actor=self.staff)
        self.assertFalse(WorkOrder.objects.filter(service_request=self.item).exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "open")

    def test_resolution_rolls_back_when_status_write_fails(self):
        service_request_assign(item=self.item, technician=self.tech, actor=self.staff)
        with patch.object(ServiceRequest, "save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                service_request_resolve(item=self.item, actor=self.tech, work_notes="Fixed")
        work_order = WorkOrder.objects.get(service_request=self.item)
        self.assertIsNone(work_order.completed_at)
        self.assertEqual(work_order.work_notes, "")


class PaginationTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        for i in range(12):
            self.make_request(title=f"Printer jam number {i:02d}")
        self.make_request(title="Printer already assigned", status="assigned")
        self.make_request(title="Projector bulb gone")

    def test_page_two_keeps_search_and_status(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("requests:list"), {"q": "Printer", "status": "open", "page": 2})
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["page_obj"].paginator.count, 12)
        self.assertEqual(response.context["query"], "Printer")
        self.assertEqual(response.context["selected_status"], "open")
        self.assertContains(response, 'value="Printer"')
        self.assertContains(response, 'value="open" selected')
        body = html.unescape(response.content.decode())
        self.assertIn("?q=Printer&status=open&page=1", body)  # Previous link

    def test_query_string_tag_replaces_only_page(self):
        request = RequestFactory().get("/requests/", {"q": "Printer", "status": "open", "page": "3", "junk": "x"})
        out = Template("{% load request_extras %}{% query_string page=2 %}").render(
            Context({"request": request}))
        params = parse_qs(urlparse(html.unescape(out)).query)
        self.assertEqual(params, {"q": ["Printer"], "status": ["open"], "page": ["2"]})

    def test_query_string_tag_omits_blank_filters(self):
        request = RequestFactory().get("/requests/", {"q": "", "status": ""})
        out = Template("{% load request_extras %}{% query_string page=2 %}").render(
            Context({"request": request}))
        self.assertEqual(out, "?page=2")


class SummaryCountTests(WorkflowBase):
    def test_non_staff_counts_cover_only_visible_requests(self):
        self.make_request(title="Second request owner", status="assigned")
        self.make_request(title="Someone else resolved", requester=self.other, status="resolved")
        self.client.force_login(self.owner)
        counts = self.client.get(reverse("requests:list")).context["counts"]
        self.assertEqual(counts, {"total": 2, "open": 1, "assigned": 1, "resolved": 0})

    def test_staff_counts_cover_everything(self):
        self.make_request(title="Second request owner", status="assigned")
        self.make_request(title="Someone else resolved", requester=self.other, status="resolved")
        self.client.force_login(self.staff)
        counts = self.client.get(reverse("requests:list")).context["counts"]
        self.assertEqual(counts, {"total": 3, "open": 1, "assigned": 1, "resolved": 1})

    def test_counts_are_rendered_above_the_list(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("requests:list")), 'aria-label="Request summary"')
