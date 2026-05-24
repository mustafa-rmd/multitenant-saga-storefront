from django.contrib import admin

from apps.iam.models import TenantMembership


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    list_filter = ("role", "tenant")
    search_fields = ("user__email", "tenant__subdomain")
    autocomplete_fields = ("user", "tenant")
