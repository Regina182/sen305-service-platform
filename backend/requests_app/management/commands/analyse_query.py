from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from requests_app.models import Category, ServiceRequest

PREFIX = "SYN-"
STATUSES = ["open", "assigned", "resolved"]


class Command(BaseCommand):
    help = "Lab 3 Task 3: seed 12 synthetic requests (2 categories, 3 statuses) and analyse a query."

    def handle(self, *args, **options):
        User = get_user_model()
        requester, _ = User.objects.get_or_create(username="requester1")
        electrical, _ = Category.objects.get_or_create(name="Electrical")
        ict, _ = Category.objects.get_or_create(name="ICT Support")

        ServiceRequest.objects.filter(title__startswith=PREFIX).delete()  # safe to re-run
        now = timezone.now()
        for i in range(12):
            status = STATUSES[i % 3]
            ServiceRequest.objects.create(
                requester=requester,
                category=electrical if i % 2 == 0 else ict,
                title=f"{PREFIX}{i:02d} synthetic request",
                description="Synthetic laboratory data.",
                location="Lab",
                priority=(i % 5) + 1,
                status=status,
                due_at=now + timedelta(days=i),
                resolved_at=now if status == "resolved" else None,
                resolution_summary="Synthetic fix." if status == "resolved" else "",
            )

        queryset = (
            ServiceRequest.objects
            .filter(category=electrical, status__in=["open", "assigned"])
            .order_by("priority", "created_at")
        )
        self.stdout.write(f"Rows returned: {queryset.count()}\n")
        self.stdout.write("--- queryset.query ---")
        self.stdout.write(str(queryset.query))
        self.stdout.write("\n--- queryset.explain() ---")
        self.stdout.write(queryset.explain())
