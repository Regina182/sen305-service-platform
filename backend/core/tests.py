from django.test import TestCase
from django.urls import reverse


class PublicPageTests(TestCase):
    def test_public_routes_return_200(self):
        for name in ("core:home", "core:about", "core:contact", "core:workflow"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_missing_route_returns_custom_404(self):
        response = self.client.get("/does-not-exist/")
        self.assertContains(response, "Page not found", status_code=404)

    def test_contact_values_come_from_view_context(self):
        response = self.client.get(reverse("core:contact"))
        for key in ("department_name", "email", "office_hours"):
            self.assertIn(key, response.context)

    def test_workflow_renders_four_stages_from_python_list(self):
        response = self.client.get(reverse("core:workflow"))
        self.assertEqual(len(response.context["stages"]), 4)
        self.assertContains(response, "Technician assigned")

    def test_about_lists_four_roles(self):
        self.assertEqual(len(self.client.get(reverse("core:about")).context["project_roles"]), 4)

    def test_active_navigation_marks_current_page_only(self):
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, 'href="/about/" aria-current="page"')
        self.assertNotContains(response, 'href="/" aria-current="page"')
        self.assertContains(self.client.get(reverse("core:contact")), 'href="/contact/" aria-current="page"')

    def test_every_page_extends_base(self):
        for name in ("core:home", "core:about", "core:contact", "core:workflow"):
            self.assertTemplateUsed(self.client.get(reverse(name)), "core/base.html")
