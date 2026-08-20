from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

# RS06 — comunicação segura. Detalhado na Phase 7.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# Sem browsable API em produção: só JSON.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
)

# ---------------------------------------------------------------- allow-lists

# ALLOWED_HOSTS e CORS vêm do ambiente (base.py). Em produção, vazio não é um
# default aceitável: sem host declarado o Django recusa tudo com 400 e ninguém
# entende por quê; CORS vazio com CORS_ALLOW_CREDENTIALS ligado é pior ainda,
# porque convida alguém a "resolver" com CORS_ALLOW_ALL_ORIGINS. Falhar no boot
# é mais barato do que descobrir isso em produção.
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS é obrigatório em produção."
    )

# Origem confiável para POST com CSRF atrás de proxy HTTPS — o Django exige o
# esquema aqui, diferente de ALLOWED_HOSTS.
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS if "*" not in host]  # noqa: F405

# Não vaza a URL interna (que carrega ids) para sites de terceiros.
SECURE_REFERRER_POLICY = "same-origin"

# Conexões persistentes: o papel e a GUC do RLS são SET LOCAL, desfeitos no
# COMMIT, então reaproveitar a conexão não carrega o usuário de uma request para
# a próxima. Ver core/rls.py.
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
