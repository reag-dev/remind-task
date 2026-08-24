from decouple import Csv, config
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


def _csrf_origin(host: str) -> str | None:
    """
    Traduz uma entrada de ALLOWED_HOSTS para a sintaxe de CSRF_TRUSTED_ORIGINS.

    As duas listas não usam a mesma notação, e a diferença é silenciosa: uma
    origem malformada não é recusada no boot — ela só nunca casa, e o POST vira
    403 sem explicação.

        example.com    ->  https://example.com
        .example.com   ->  https://*.example.com   (o ponto é o curinga de ALLOWED_HOSTS)
        *.example.com  ->  https://*.example.com   (já é a notação do CSRF)
        *              ->  descartado — "qualquer origem" não é config de produção
    """
    if host == "*":
        return None
    if host.startswith("."):
        return f"https://*{host}"
    return f"https://{host}"


# Derivar de ALLOWED_HOSTS cobre o caso comum (mesmo domínio, atrás de proxy
# HTTPS). Quem tem front em outro domínio informa a lista explicitamente.
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv()) or [
    origin for origin in map(_csrf_origin, ALLOWED_HOSTS) if origin  # noqa: F405
]

if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured(
        "CORS_ALLOWED_ORIGINS é obrigatório em produção: o frontend está em "
        "outra origem e nenhuma chamada da SPA passaria."
    )

# ------------------------------------------------------- cookie de refresh

# A topologia decidida na Phase 0 é `*.up.railway.app` para os dois serviços.
# `up.railway.app` está na Public Suffix List, então `web-xxxx.up.railway.app` e
# `front-yyyy.up.railway.app` são **registrable domains diferentes** — não é o
# caso "mesmo site" que o SameSite=Lax cobre. Com Lax, o cookie de refresh
# simplesmente não seria enviado, e a sessão morreria a cada 15 minutos sem erro
# nenhum: o usuário só cairia na tela de login.
AUTH_COOKIE_SAMESITE = config("AUTH_COOKIE_SAMESITE", default="None")

_SAMESITE_VALIDOS = {"Lax", "Strict", "None"}
if AUTH_COOKIE_SAMESITE not in _SAMESITE_VALIDOS:
    raise ImproperlyConfigured(
        f"AUTH_COOKIE_SAMESITE={AUTH_COOKIE_SAMESITE!r} não é válido; "
        f"use um de {sorted(_SAMESITE_VALIDOS)}."
    )

# `None` sem `Secure` é a combinação que o browser descarta **em silêncio**: o
# cookie não é recusado com erro, ele só nunca chega. Falhar no boot é a única
# forma de isso não virar um bug de sessão intermitente em produção — mesmo
# padrão que ALLOWED_HOSTS vazio, logo acima.
if AUTH_COOKIE_SAMESITE == "None" and not AUTH_COOKIE_SECURE:  # noqa: F405
    raise ImproperlyConfigured(
        "AUTH_COOKIE_SAMESITE='None' exige AUTH_COOKIE_SECURE=True; sem Secure "
        "o browser descarta o cookie sem avisar."
    )

# Não vaza a URL interna (que carrega ids) para sites de terceiros.
SECURE_REFERRER_POLICY = "same-origin"

# Conexões persistentes: o papel e a GUC do RLS são SET LOCAL, desfeitos no
# COMMIT, então reaproveitar a conexão não carrega o usuário de uma request para
# a próxima. Ver core/rls.py.
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
