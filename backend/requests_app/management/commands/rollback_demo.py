from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from requests_app.models import Category, ServiceRequest, WorkOrder


class Command(BaseCommand):
    help = "Lab 4 Part K: prove that a WorkOrder write and a status write roll back together."

    def handle(self, *args, **options):
        User = get_user_model()
        technician, _ = User.objects.get_or_create(
            username="technician1", defaults={"is_staff": True}
        )
        item = ServiceRequest.objects.filter(status="open").first()
        if item is None:  # nothing to experiment on: create one synthetic request
            requester, _ = User.objects.get_or_create(username="requester1")
            category, _ = Category.objects.get_or_create(name="ICT Support")
            item = ServiceRequest.objects.create(
                requester=requester, category=category, title="RB-synthetic rollback test",
                description="Synthetic laboratory data.", location="Lab",
            )

        before_status = item.status
        before_count = WorkOrder.objects.filter(service_request=item).count()
        try:
            with transaction.atomic():
                WorkOrder.objects.create(service_request=item, technician=technician)
                item.status = "assigned"
                item.save(update_fields=["status", "updated_at"])
                raise RuntimeError("Deliberate failure for rollback test")
        except RuntimeError as exc:  # caught OUTSIDE the atomic block
            self.stdout.write(str(exc))

        item.refresh_from_db()
        after_count = WorkOrder.objects.filter(service_request=item).count()
        self.stdout.write(f"status: {before_status} -> {item.status}")
        self.stdout.write(f"work orders: {before_count} -> {after_count}")
