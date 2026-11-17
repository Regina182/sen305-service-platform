from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from requests_app.models import Category, Comment, ServiceRequest


class ServiceRequestCrudTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="pass12345")
        self.other = User.objects.create_user("other", password="pass12345")
        self.staff = User.objects.create_user("staff", password="pass12345", is_staff=True)
        self.category = Category.objects.create(name="Facilities")
        self.item = ServiceRequest.objects.create(
            requester=self.owner, category=self.category,
            title="Projector does not display",
            description="The projector reports no HDMI signal.",
            location="Room B12", priority=3,
        )

    def payload(self, **overrides):
        data = {
            "category": self.category.id,
            "title": "Air conditioner leaks water",
            "description": "Water drips near the laboratory entrance.",
            "location": "Software Laboratory", "priority": 2,
        }
        data.update(overrides)
        return data

    # ---- the five Lab 4 tests ----
    def test_list_requires_login(self):
        response = self.client.get(reverse("requests:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_owner_can_open_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.title)

    def test_other_requester_receives_404(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertEqual(response.status_code, 404)

    def test_valid_post_creates_request_for_logged_in_user(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("requests:create"), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ServiceRequest.objects.filter(
            requester=self.owner, title="Air conditioner leaks water"
        ).exists())

    def test_invalid_post_does_not_create_request(self):
        self.client.force_login(self.owner)
        before = ServiceRequest.objects.count()
        response = self.client.post(reverse("requests:create"), self.payload(
            title="Short", description="", location=""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ServiceRequest.objects.count(), before)
        self.assertContains(response, "Use at least 8 characters.")

    # ---- extra authorization / CRUD coverage ----
    def test_requester_cannot_be_forged_through_post(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("requests:create"), self.payload(requester=self.other.id))
        created = ServiceRequest.objects.get(title="Air conditioner leaks water")
        self.assertEqual(created.requester, self.owner)

    def test_owner_can_edit_open_request(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("requests:update", args=[self.item.id]),
            self.payload(title="Projector HDMI port is dead", location="Room B14"),
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, "Projector HDMI port is dead")
        self.assertEqual(self.item.location, "Room B14")

    def test_owner_cannot_edit_after_assignment(self):
        ServiceRequest.objects.filter(id=self.item.id).update(status="assigned")
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("requests:update", args=[self.item.id]), self.payload(title="Changed title here"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only an open request can be edited.")
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, "Projector does not display")

    def test_other_requester_cannot_edit(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("requests:update", args=[self.item.id]), self.payload())
        self.assertEqual(response.status_code, 404)

    def test_staff_can_open_any_request(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)

    def test_comment_author_comes_from_logged_in_user(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("requests:comment-add", args=[self.item.id]), {"body": "Still broken today"})
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(service_request=self.item)
        self.assertEqual(comment.author, self.owner)
        self.assertFalse(comment.is_internal)

    def test_comment_endpoint_requires_post(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("requests:comment-add", args=[self.item.id]))
        self.assertEqual(response.status_code, 405)

    def test_other_requester_cannot_comment(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("requests:comment-add", args=[self.item.id]), {"body": "Sneaky comment"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.count(), 0)

    def test_internal_comments_hidden_from_requester(self):
        Comment.objects.create(
            service_request=self.item, author=self.staff, body="Internal staff note", is_internal=True)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertNotContains(response, "Internal staff note")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertContains(response, "Internal staff note")
