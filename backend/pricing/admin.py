
from django.contrib import admin
from solo.admin import SingletonModelAdmin

from pricing.models import PricingConfiguration

admin.site.register(PricingConfiguration, SingletonModelAdmin)