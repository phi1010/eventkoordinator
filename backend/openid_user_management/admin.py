"""
Django admin configuration for OpenID User Management.

Provides a customized admin interface for managing OpenID users.
"""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as OrigGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils.translation import gettext_lazy as _

from .models import OpenIDUser


@admin.register(OpenIDUser)
class OpenIDUserAdmin(BaseUserAdmin):
    """
    Custom admin interface for OpenIDUser model.

    Configured to work with email-based authentication and UUID primary key.
    """

    # Fields displayed in the list view
    list_display = ('username', 'email', 'openid_provider', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'openid_provider', 'date_joined')
    search_fields = ('username', 'email', 'openid_subject')
    ordering = ('-date_joined',)

    # Fieldsets for the detail view
    fieldsets = (
        (None, {
            'fields': ('id', 'username', 'email', 'password')
        }),
        (_('Personal Info'), {
            'fields': ('phone_number', 'picture', 'locale')
        }),
        (_('OpenID Connect'), {
            'fields': ('openid_subject', 'openid_provider'),
            'classes': ('collapse',)
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        (_('Important dates'), {
            'fields': ('date_joined', 'last_login')
        }),
    )

    # Fieldsets for the add view
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        (_('Permissions'), {
            'classes': ('wide',),
            'fields': ('is_active', 'is_staff', 'is_superuser'),
        }),
    )

    # Read-only fields
    readonly_fields = ('id', 'date_joined', 'last_login')

    # Filter for active users
    actions = ['make_active', 'make_inactive']

    def make_active(self, request, queryset):
        """Mark selected users as active."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} user(s) marked as active.')
    make_active.short_description = 'Mark selected users as active'

    def make_inactive(self, request, queryset):
        """Mark selected users as inactive."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} user(s) marked as inactive.')
    make_inactive.short_description = 'Mark selected users as inactive'


class GroupAdminForm(forms.ModelForm):
    """
    ModelForm that adds an additional multiple select field for managing
    the users in the group.
    """
    users = forms.ModelMultipleChoiceField(
        OpenIDUser.objects.all(),
        widget=admin.widgets.FilteredSelectMultiple('Users', False),
        required=False,
        )


    def __init__(self, *args, **kwargs):
        super(GroupAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            initial_users = self.instance.user_set.values_list('pk', flat=True)
            self.initial['users'] = initial_users


    def save(self, *args, **kwargs):
        kwargs['commit'] = True
        return super(GroupAdminForm, self).save(*args, **kwargs)


    def save_m2m(self):
        self.instance.user_set.clear()
        self.instance.user_set.add(*self.cleaned_data['users'])

admin.site.unregister(Group)  # Unregister the default Group admin
@admin.register(Group)
class GroupAdmin(OrigGroupAdmin):
    """
    Customized GroupAdmin class that uses the customized form to allow
    management of users within a group.
    """
    form = GroupAdminForm
