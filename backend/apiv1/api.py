"""
Main API module.
This module initializes the NinjaAPI instance and registers all routers
organized by domain (auth, lookups, series, proposals, speakers, sync, calendar).
"""

from ninja import NinjaAPI
from ninja.security import django_auth

from openid_user_management import api as openid_user_management_router

# Import all routers
from apiv1.routers import auth as auth_router
from apiv1.routers import lookups as lookups_router
from apiv1.routers import series as series_router
from apiv1.routers import proposals as proposals_router
from apiv1.routers import speakers as speakers_router
from apiv1.routers import sync as sync_router
from apiv1.routers import calendar as calendar_router
from apiv1.routers import calculated_prices as calculated_prices_router

# Initialize the main API instance with Django auth as default
api = NinjaAPI(auth=django_auth)
# Register routers with the API instance
api.add_router("/", auth_router.router, tags=["auth"])
api.add_router("/", lookups_router.router, tags=["lookups"])
api.add_router("/series", series_router.router, tags=["series"])
api.add_router("/proposals", proposals_router.router, tags=["proposals"])
api.add_router("/proposals", speakers_router.router, tags=["speakers"])
api.add_router("/sync", sync_router.router, tags=["sync"])
api.add_router("/calendar", calendar_router.router, tags=["calendar"])
api.add_router("/pricing", calculated_prices_router.router, tags=["calculated-prices"])
api.add_router("/user", openid_user_management_router.router, tags=["user"])


# Health check endpoint
@api.get("/health", auth=None)
def health_check(request):
    """Health check endpoint"""
    return {"status": "ok"}
