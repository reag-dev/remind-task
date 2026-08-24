from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("tables.urls")),
    path("api/", include("records.urls")),
    path("api/", include("alerts.urls")),
]

# As duas superfícies abaixo são montadas condicionalmente, e não protegidas por
# permissão dentro da view: uma rota que não existe devolve 404 e não confirma
# nada. Uma que existe e responde 403 já contou que o Admin está ali.
if settings.EXPOSE_ADMIN:
    urlpatterns.append(path("admin/", admin.site.urls))

if settings.EXPOSE_API_DOCS:
    urlpatterns += [
        # O schema anda junto com a UI de propósito: publicar `/api/schema/`
        # sozinho entrega a planta inteira, que é o que interessa a quem sonda —
        # a página do Swagger é só a apresentação dela.
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
    ]
