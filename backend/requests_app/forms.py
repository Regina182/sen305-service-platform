from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Category, Comment, ServiceRequest

PRIORITY_CHOICES = [
    (1, "1 - Highest"),
    (2, "2 - High"),
    (3, "3 - Medium"),
    (4, "4 - Low"),
    (5, "5 - Lowest"),
]


class ServiceRequestForm(forms.ModelForm):
    priority = forms.TypedChoiceField(choices=PRIORITY_CHOICES, coerce=int, initial=3)

    class Meta:
        model = ServiceRequest
        # requester, status and resolved_at are deliberately NOT exposed:
        # they are set from request.user or by workflow services.
        fields = ["category", "title", "description", "location", "priority"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Active categories only, plus the category already on an existing request.
        self.fields["category"].queryset = Category.objects.filter(
            Q(is_active=True) | Q(pk=self.instance.category_id)
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 8:
            raise forms.ValidationError("Use at least 8 characters.")
        return title


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]  # author comes from request.user; is_internal is not exposed
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if len(body) < 3:
            raise forms.ValidationError("Enter a meaningful comment.")
        return body


class AssignmentForm(forms.Form):
    technician = forms.ModelChoiceField(queryset=get_user_model().objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["technician"].queryset = get_user_model().objects.filter(
            is_active=True, is_staff=True
        ).order_by("username")


class ResolutionForm(forms.Form):
    work_notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=True)

    def clean_work_notes(self):
        notes = self.cleaned_data["work_notes"].strip()
        if not notes:
            raise forms.ValidationError("Describe the work that was done.")
        return notes
