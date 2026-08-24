"""
Settings comuns a todos os ambientes.

Nada aqui pode assumir DEBUG=True. Ajustes de ambiente ficam em dev.py / prod.py.
"""

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import dj_database_url
from celery.schedules import crontab
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY")

# Superfícies que não são a API em si. Ligadas por padrão porque em
# desenvolvimento são ferramenta de trabalho; `prod.py` inverte os dois
# defaults — publicá-las é escolha, não consequência de subir o serviço.
# Guardas de superfície HTTP: desligadas por padrão, `prod.py` liga.
#
# Em desenvolvimento, ALLOWED_HOSTS e CORS vazios são um começo legítimo, e
# derrubar o `runserver` por causa deles só atrapalha. Ver config/validacao.py.
VALIDAR_SUPERFICIE_HTTP = False

EXPOSE_ADMIN = config("EXPOSE_ADMIN", default=True, cast=bool)
EXPOSE_API_DOCS = config("EXPOSE_API_DOCS", default=True, cast=bool)
DEBUG = False
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())

# O Railway só conhece o domínio público do serviço depois de criá-lo, e ele
# muda se o serviço for recriado. Deixar que a plataforma se anuncie evita a
# volta clássica: deploy verde, e todo request respondendo 400 DisallowedHost
# porque ninguém copiou o domínio novo para a variável.
_railway_domain = config("RAILWAY_PUBLIC_DOMAIN", default="")
if _railway_domain and _railway_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, _railway_domain]

# O healthcheck da plataforma NÃO chega pelo domínio público: ele bate no
# container pela rede interna, e o Host que manda é este nome fixo. Sem ele na
# lista, o Django responde 400 (DisallowedHost) ao healthcheck, o Railway marca
# o deploy como reprovado e o domínio passa a devolver 502 — com o container de
# pé e a aplicação saudável, que é o que torna o sintoma tão confuso.
#
# A condição para isto entrar é ter ALGUM host configurado — não a presença de
# `RAILWAY_PUBLIC_DOMAIN`.
#
# A primeira versão dependia dela, e era frágil de um jeito específico: se a
# plataforma não injetasse essa variável no serviço (porque o domínio foi criado
# depois, porque o serviço foi recriado, por qualquer motivo), a linha não
# rodava e a correção não fazia NADA — em silêncio, sem erro, sem log. Ficava
# indistinguível de não ter sido aplicada, que é o pior tipo de correção.
#
# `ALLOWED_HOSTS` não-vazio é o sinal certo: significa que este processo atende
# HTTP em algum lugar configurado, e todo lugar assim pode receber healthcheck.
# Em desenvolvimento a lista é vazia e nada muda.
#
# Aceitar um Host que não é nosso tem custo: `request.build_absolute_uri()`
# passaria a montar URL apontando para `healthcheck.railway.app`. Hoje nada no
# projeto monta URL a partir do Host — mas a recuperação de senha da Phase 10
# vai gerar link por e-mail, e ali o endereço tem que sair de configuração, não
# do cabeçalho da requisição.
RAILWAY_HEALTHCHECK_HOST = "healthcheck.railway.app"
if ALLOWED_HOSTS and RAILWAY_HEALTHCHECK_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, RAILWAY_HEALTHCHECK_HOST]

# ---------------------------------------------------------------- apps

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Necessário para a operação CreateCollation da migration accounts.0001.
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # RS07: invalidação de refresh
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "axes",  # RS03: rate limit de login
]

LOCAL_APPS = [
    "core",
    "accounts",
    "tables",
    "records",
    "alerts",
    "exports",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Imediatamente após o SecurityMiddleware, como a doc do WhiteNoise exige:
    # os estáticos são servidos sem pagar o resto da pilha, mas ainda depois dos
    # redirects e headers de segurança — servir estático em http:// puro
    # anularia o SECURE_SSL_REDIRECT.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # AxesMiddleware precisa vir DEPOIS do AuthenticationMiddleware.
    "axes.middleware.AxesMiddleware",
    # RS01 — o mais INTERNO da lista: devolve a conexão ao papel de login no fim
    # da request, antes de qualquer middleware externo escrever no banco.
    "core.middleware.RowLevelSecurityMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------- database

# DATABASE_URL é o que plataformas gerenciadas (Railway) injetam; os POSTGRES_*
# são o caminho do compose de desenvolvimento. A URL vence quando existe, e o
# compose não regride.
_database_url = config("DATABASE_URL", default="")

if _database_url:
    _default_db = dj_database_url.parse(_database_url)
else:
    _default_db = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }

# ATOMIC_REQUESTS é aplicado DEPOIS, e fora do if, de propósito.
#
# `dj_database_url.parse()` devolve um dicionário novo — escrever
# `DATABASES["default"] = parse(...)` é a forma óbvia de perder esta chave sem
# que nada reclame, porque a RLS só falha em runtime: a GUC app.user_id é setada
# com SET LOCAL, que exige uma transação aberta. Sem ATOMIC_REQUESTS o SET LOCAL
# morre no autocommit e o isolamento cai para a camada de queryset.
# `tests/security/test_cookie_policy.py` trava isto nos dois caminhos.
_default_db["ATOMIC_REQUESTS"] = True

DATABASES = {"default": _default_db}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- auth

# RS03 — Argon2id como hasher primário (depende de argon2-cffi).
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

# django-axes intercepta authenticate() e conta as falhas. O AxesStandaloneBackend
# precisa vir PRIMEIRO: é ele que levanta PermissionDenied quando a conta está
# bloqueada, antes do ModelBackend chegar a conferir a senha.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ---------------------------------------------------------------- jwt (RS07)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Rotação + blacklist: cada refresh emite um par novo e queima o anterior.
    # Sem isso, um refresh token vazado vale 7 dias inteiros mesmo após logout.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Refresh token vai em cookie httpOnly, nunca em localStorage nem no corpo da
# resposta: JS da página não consegue lê-lo, o que tira o XSS do jogo.
AUTH_COOKIE_NAME = "refresh_token"
# Vem do ambiente para que a guarda de prod.py (SameSite=None exige Secure)
# seja testável: um valor que só existe como literal no código não tem como ser
# exercitado pelo caminho de erro. dev.py sobrescreve para permitir
# http://localhost, que não é origem segura.
AUTH_COOKIE_SECURE = config("AUTH_COOKIE_SECURE", default=True, cast=bool)
AUTH_COOKIE_HTTPONLY = True
AUTH_COOKIE_SAMESITE = "Lax"
AUTH_COOKIE_PATH = "/api/auth/"

# ---------------------------------------------------------------- axes (RS03)

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
# Bloqueia a combinação IP+usuário: não deixa um atacante trancar a conta alheia
# só errando a senha dela de fora (DoS de conta), nem varrer contas de um só IP.
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_FORM_FIELD = "email"
AXES_LOCKOUT_CALLABLE = None
AXES_ENABLE_ADMIN = True

# ---------------------------------------------------------------- i18n / tz

LANGUAGE_CODE = "pt-br"
# Servidor sempre em UTC. A conversão para o fuso do usuário (users.timezone)
# acontece na camada de aplicação — ver nota 4 do modelo de dados.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Comprime e versiona por hash no `collectstatic`, o que permite cache
    # longo. "Manifest" é o detalhe que morde: um arquivo referenciado e
    # ausente vira erro no collectstatic, no build — e não um 500 em produção.
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# ---------------------------------------------------------------- DRF

REST_FRAMEWORK = {
    # RS01 — as subclasses com prefixo RLS entram no papel `remind_app` assim
    # que a autenticação identifica o usuário. É o primeiro ponto do ciclo em
    # que se sabe QUEM está pedindo, e (com ATOMIC_REQUESTS) já está dentro da
    # transação que o SET LOCAL exige. Ver core/rls.py.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.rls.RLSJWTAuthentication",
        # Session fica só para a Browsable API e o Admin.
        "core.rls.RLSSessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    # Subclasse própria: expõe `?page_size=` com teto de 200. O padrão do DRF
    # ignora o parâmetro em silêncio, e um seletor de "linhas por página" no
    # cliente pareceria funcionar sem funcionar. Ver core/pagination.py.
    "DEFAULT_PAGINATION_CLASS": "core.pagination.PaginacaoPadrao",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # RS —  limite de taxa. O `django-axes` cobre só o login, por tentativa de
    # senha; tudo o mais estava sem teto nenhum.
    #
    # `user` e `anon` valem para toda view. A exportação tem teto próprio,
    # declarado na própria action — ver `core.throttling.ExportacaoThrottle`.
    # Subclasses próprias, não as do DRF: elas liberam a requisição quando o
    # cache não responde, em vez de devolver 500. Ver core/throttling.py — o
    # motivo está escrito lá, e é o que impede esta phase de transformar uma
    # queda do Redis em queda da aplicação.
    "DEFAULT_THROTTLE_CLASSES": (
        "core.throttling.UsuarioThrottle",
        "core.throttling.AnonimoThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": config("THROTTLE_USER", default="1000/hour"),
        # Anônimo é bem mais apertado: sem sessão, os únicos caminhos abertos
        # são login, registro e health — nenhum deles tem uso legítimo em
        # rajada.
        "anon": config("THROTTLE_ANON", default="60/hour"),
        # O export transmite a queryset INTEIRA em streaming, sem paginar — é o
        # endpoint mais caro do sistema por larga margem. Um teto separado
        # impede que ele consuma a cota geral do usuário e, principalmente, que
        # alguém o use em laço.
        "export": config("THROTTLE_EXPORT", default="20/hour"),
    },
    # Sem isto, o limite anônimo é contornável trivialmente.
    #
    # O `get_ident` do DRF, quando `NUM_PROXIES` é None, usa o cabeçalho
    # `X-Forwarded-For` INTEIRO como identidade. Quem manda um XFF diferente a
    # cada request vira um cliente novo a cada request, e o teto nunca é
    # alcançado. Com o número de proxies declarado, o DRF conta de trás para
    # frente e pega o endereço que o proxy escreveu — o único que o cliente não
    # controla. Em produção, atrás do proxy da plataforma, é 1.
    "NUM_PROXIES": config("NUM_PROXIES", default=None, cast=lambda v: int(v) if v else None),
}

# ---------------------------------------------------------------- cache

# O throttle guarda os contadores no cache. Com o LocMemCache padrão, cada
# worker do gunicorn teria o SEU contador: três workers, três vezes o limite
# configurado — e tudo zerado a cada deploy. O teto pareceria valer sem valer.
#
# DB 1 para não dividir espaço de chaves com o Celery, que usa a 0.
def _redis_db(url: str, db: int) -> str:
    """
    Troca o número do banco numa URL de Redis.

    Feito com `urlparse`, e não com `str.replace("/0", "/1")`: a substituição
    ingênua acerta o caso comum e erra calado quando a URL não traz banco
    (`redis://host:6379`) ou quando `/0` aparece na senha — e o resultado é a
    aplicação usando o mesmo banco do Celery, ou uma URL inválida.
    """
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{db}"))


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        # DB 1 para não dividir espaço de chaves com o Celery, que usa a 0.
        "LOCATION": config(
            "CACHE_URL",
            default=_redis_db(config("REDIS_URL", default="redis://redis:6379/0"), 1),
        ),
    }
}

SPECTACULAR_SETTINGS = {
    "TITLE": "remind-task API",
    "DESCRIPTION": "Tabelas dinâmicas com controle de vencimentos e alertas.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------- celery

CELERY_BROKER_URL = config("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# ---------------------------------------------------------------- e-mail

# Provedor decidido na Phase 0: Resend, falando SMTP. A amarração a fornecedor
# fica só na credencial — trocar de provedor é trocar host, usuário e senha.
#
# O default é o backend de CONSOLE, e isso é deliberado: sem credencial, o
# e-mail aparece no terminal em vez de estourar. Em desenvolvimento é o
# comportamento útil, e num deploy mal configurado é infinitamente melhor que a
# alternativa — um SMTP que tenta conectar, trava e derruba o worker.
#
# ⚠️ Verificar o domínio (SPF/DKIM) no painel do Resend ANTES de confiar no
# envio real. Sem isso a entrega falha ou cai em spam, e nada nos testes revela
# isso: eles usam o backend `locmem`, que aceita qualquer coisa.
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.resend.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
# No Resend o usuário é a string literal "resend" e a senha é a API key.
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="resend")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

# Sem timeout, `smtplib` espera pelo default do sistema — que em Linux passa de
# dois minutos. Um provedor que aceita a conexão e não responde prenderia o
# worker nesse tempo por e-mail, e a fila inteira pararia atrás de um SMTP
# lento. O envio precisa desistir muito antes disso.
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)

# Precisa ser um endereço no domínio verificado no provedor; qualquer outro é
# recusado no envio, não na configuração.
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="alertas@localhost")

# Quantas vezes tentar entregar antes de desistir, e o intervalo mínimo entre
# tentativas. O backoff é exponencial em minutos (2, 4, 8, 16…): provedor fora
# do ar não pode virar uma fila que se repete a cada execução do cron.
EMAIL_MAX_ATTEMPTS = config("EMAIL_MAX_ATTEMPTS", default=5, cast=int)
EMAIL_RETRY_BASE_MINUTES = config("EMAIL_RETRY_BASE_MINUTES", default=2, cast=int)

# ---------------------------------------------------------------- cors

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# RF13 — sem isto o browser ESCONDE o `Content-Disposition` do JavaScript numa
# resposta cross-origin, e o CSV baixa com o nome genérico da URL em vez de
# `contratos-2026-08-20.csv`. O header não é secreto: ele já vai na resposta, e
# a política só decide se o script da página pode lê-lo.
#
# A lista é explícita e curta de propósito. Expor cabeçalhos em massa (ou `*`)
# entregaria a scripts de outra origem coisas como `Vary` e headers de
# infraestrutura que não são da conta deles.
CORS_EXPOSE_HEADERS = ["Content-Disposition"]

# ---------------------------------------------------------------- logging

# RS05 — RedactingFilter apaga credenciais, JWTs, hashes de senha e o `data`
# dos registros antes de qualquer handler formatar a linha. Ver core/logging.py.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "filters": {
        "redact": {"()": "core.logging.RedactingFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["redact"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Varredura de vencimentos (RF12). A cada 15 minutos: a granularidade do sistema
# é o DIA, então o intervalo só precisa ser curto o bastante para que a virada
# do dia em qualquer fuso seja notada logo. Repetição é inofensiva — a
# constraint alerts_idempotency impede duplicata.
CELERY_BEAT_SCHEDULE = {
    "scan-due-records": {
        "task": "alerts.scan_due_records",
        "schedule": crontab(minute="*/15"),
    },
    # Entrega separada da geração: um provedor de e-mail fora do ar não pode
    # parar a emissão dos alertas in-app, que não dependem de rede.
    #
    # Defasada em 5 minutos para não disputar o worker com a varredura, e por
    # ordem natural — quando esta roda, os pendentes que a varredura acabou de
    # criar já estão no banco.
    "send-pending-emails": {
        "task": "alerts.send_pending_emails",
        "schedule": crontab(minute="5-59/15"),
    },
}
