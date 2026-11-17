from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from requests_app.models import Category, ServiceRequest, WorkOrder


class ServiceRequestModelTests(TestCase):

    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(username="requester")
        self.technician = user_model.objects.create_user(username="technician")
        self.category = Category.objects.create(name="Electrical")

    def make_request(self, **overrides):
        values = {
            "requester": self.requester, "category": self.category,
            "title": "Faulty socket", "description": "Socket does not supply power.",
            "location": "Software Engineering Lab", "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest.objects.create(**values)

    def build(self, **overrides):
        values = {
            "requester": self.requester, "category": self.category,
            "title": "Rule test", "description": "Testing the resolution rule.",
            "location": "Lab", "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest(**values)

    # ---- Lab 3 originals ----
    def test_default_status_is_open(self):
        self.assertEqual(self.make_request().status, ServiceRequest.Status.OPEN)

    def test_priority_validator_rejects_zero(self):
        with self.assertRaises(ValidationError):
            self.build(priority=0).full_clean()

    def test_database_constraint_rejects_priority_six(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_request(priority=6)

    def test_category_in_use_is_protected(self):
        self.make_request()
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_request_accepts_only_one_work_order(self):
        item = self.make_request()
        WorkOrder.objects.create(service_request=item, technician=self.technician)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkOrder.objects.create(service_request=item, technician=self.technician)

    # ---- Exercise Task 1: due date ----
    def test_due_at_is_optional(self):
        self.assertIsNone(self.make_request().due_at)

    def test_query_requests_due_before_chosen_time(self):
        now = timezone.now()
        soon = self.make_request(title="Due soon", due_at=now + timedelta(hours=2))
        later = self.make_request(title="Due later", due_at=now + timedelta(days=3))
        self.make_request(title="No due date")
        due = ServiceRequest.objects.filter(due_at__lt=now + timedelta(days=1))
        self.assertEqual(list(due), [soon])
        self.assertNotIn(later, due)

    def test_status_due_index_is_declared(self):
        self.assertIn("req_status_due_idx", [i.name for i in ServiceRequest._meta.indexes])

    # ---- Exercise Task 2: resolution rule ----
    def test_resolved_without_resolved_at_fails(self):
        item = self.build(status="resolved", resolution_summary="Replaced socket.")
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolved_at", ctx.exception.message_dict)

    def test_resolved_without_summary_fails(self):
        item = self.build(status="resolved", resolved_at=timezone.now())
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_whitespace_summary_is_rejected(self):
        item = self.build(status="closed", resolved_at=timezone.now(), resolution_summary="   ")
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_closed_requires_both_fields(self):
        with self.assertRaises(ValidationError) as ctx:
            self.build(status="closed").full_clean()
        self.assertEqual(set(ctx.exception.message_dict), {"resolved_at", "resolution_summary"})

    def test_resolved_with_both_fields_is_valid(self):
        self.build(
            status="resolved", resolved_at=timezone.now(),
            resolution_summary="Replaced the damaged socket.",
        ).full_clean()

    def test_open_and_assigned_need_no_summary(self):
        self.build(status="open").full_clean()
        self.build(status="assigned").full_clean()
