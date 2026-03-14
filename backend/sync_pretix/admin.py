
from django.contrib import admin
from django.contrib.admin import ModelAdmin

from sync_pretix.models import CalculatedPrices, PretixPricingConfiguration

admin.site.register(PretixPricingConfiguration, ModelAdmin)
admin.site.register(CalculatedPrices, ModelAdmin)
