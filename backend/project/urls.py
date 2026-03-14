"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include, re_path
from django.views.generic import RedirectView

import apiv1.api
from project.spa_views import SpaFallbackView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/docs/", RedirectView.as_view(url="/api/v1/docs", permanent=False)),
    path("api/v1/", apiv1.api.api.urls),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("", include("django_prometheus.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    # SPA catch-all: any URL not matched above is handled by React-Router.
    # Must be last so it never shadows the real API or admin routes.
    re_path(r"^.*$", SpaFallbackView.as_view(), name="spa-fallback"),
]
