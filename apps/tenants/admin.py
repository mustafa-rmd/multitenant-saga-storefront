from django.contrib import admin

from apps.tenants.models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("subdomain", "name", "default_currency", "is_active", "created_at")
    search_fields = ("subdomain", "name")
    list_filter = ("is_active", "default_currency")
