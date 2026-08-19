from decouple import config

from .base import *  # noqa: F403

DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)

# http://localhost não é origem segura — cookie Secure não seria enviado de volta.
AUTH_COOKIE_SECURE = False

# Browsable API do DRF é a "UI" do MVP — ver Out-of-Scope do plano.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)
