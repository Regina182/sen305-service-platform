from django.shortcuts import render

from requests_app.models import ServiceRequest


def home(request):
    done = [ServiceRequest.Status.RESOLVED, ServiceRequest.Status.CLOSED]
    context = {
        "platform_name": "VUA ServiceDesk",
        "headline": "Report and track maintenance requests",
        "active_requests": ServiceRequest.objects.exclude(status__in=done).count(),
    }
    return render(request, "core/home.html", context)


def about(request):
    project_roles = ["Requester", "Coordinator", "Technician", "Administrator"]
    return render(request, "core/about.html", {"project_roles": project_roles})


def contact(request):
    context = {
        "department_name": "Department of Software Engineering",
        "email": "servicedesk@example.edu",
        "office_hours": "Monday to Friday, 8:00 to 16:00",
    }
    return render(request, "core/contact.html", context)


def workflow(request):
    stages = [
        "Request submitted",
        "Request triaged",
        "Technician assigned",
        "Request resolved",
    ]
    return render(request, "core/workflow.html", {"stages": stages})
