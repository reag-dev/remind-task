from decouple import Csv, config

from .base import *  # noqa: F403

DEBUG = False

# RS06 — comunicação segura. Detalhado na Phase 7.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# O healthcheck da plataforma é a exceção, e precisa ser exceção.
#
# Ele não passa pelo proxy público: bate no container pela rede interna, em HTTP
# puro e sem `X-Forwarded-Proto`. Para o `SECURE_PROXY_SSL_HEADER` acima, isso é
# uma requisição insegura, e o `SECURE_SSL_REDIRECT` responde 301. O Railway
# espera 200, reprova o deploy, e o domínio devolve 502 com a aplicação
# perfeitamente de pé.
#
# A saída tentadora é desligar o SECURE_SSL_REDIRECT — foi o que resolveu o
# problema em metade dos relatos que se acha sobre isto, e é caro: derruba o
# redirect para TODA a aplicação por causa de um endpoint. Isentar só o caminho
# do health mantém a garantia onde ela vale.
#
# O padrão casa contra `request.path` SEM a barra inicial, e com `re.search` —
# daí o `^...$`, sem o qual `api/health/` casaria dentro de outras rotas.
# `views.health` não devolve nada que não possa trafegar em claro dentro da
# rede da plataforma: um status e se o banco respondeu.
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
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
# default aceitável — mas a checagem NÃO mora aqui.
#
# Ela morava, e o efeito era que todo processo que carregasse este módulo a
# executava. O Celery carrega: um worker, que não atende requisição nenhuma, se
# recusava a subir por falta de uma lista de origens CORS. Agora as guardas de
# superfície HTTP rodam no carregamento do WSGI — ver `config/validacao.py`,
# que explica por que aquele é o gatilho certo.
VALIDAR_SUPERFICIE_HTTP = True


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


# O host do healthcheck sai da derivação, e isto é correção de um vazamento.
#
# Ele entrou em ALLOWED_HOSTS para o healthcheck da plataforma não levar 400
# (ver base.py). Só que CSRF_TRUSTED_ORIGINS é derivado dali quando não vem
# declarado — e o efeito foi passar a confiar em `https://healthcheck.railway.app`
# para fins de CSRF. Um domínio que não é nosso, num lugar onde a lista existe
# justamente para dizer de quem aceitamos POST.
#
# Sem consequência prática hoje (o healthcheck só faz GET, e em produção a lista
# vem declarada), mas é exatamente o tipo de acréscimo silencioso que a
# igualdade estrita de `tests/security/test_transport.py` existe para pegar —
# e pegou.
_hosts_para_csrf = [
    host
    for host in ALLOWED_HOSTS  # noqa: F405
    if host != RAILWAY_HEALTHCHECK_HOST  # noqa: F405
]

# Derivar de ALLOWED_HOSTS cobre o caso comum (mesmo domínio, atrás de proxy
# HTTPS). Quem tem front em outro domínio informa a lista explicitamente.
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv()) or [
    origin for origin in map(_csrf_origin, _hosts_para_csrf) if origin
]

# ------------------------------------------------------- cookie de refresh

# A topologia decidida na Phase 0 é `*.up.railway.app` para os dois serviços.
# `up.railway.app` está na Public Suffix List, então `web-xxxx.up.railway.app` e
# `front-yyyy.up.railway.app` são **registrable domains diferentes** — não é o
# caso "mesmo site" que o SameSite=Lax cobre. Com Lax, o cookie de refresh
# simplesmente não seria enviado, e a sessão morreria a cada 15 minutos sem erro
# nenhum: o usuário só cairia na tela de login.
AUTH_COOKIE_SAMESITE = config("AUTH_COOKIE_SAMESITE", default="None")

# A validação do par (SameSite, Secure) está em `config/validacao.py`, junto com
# as demais guardas de superfície HTTP.

# --------------------------------------------------- superfície pública

# O schema OpenAPI é a planta da API: rotas, campos, formatos e mensagens de
# erro, tudo num arquivo. É excelente durante o desenvolvimento e é
# reconhecimento pronto para quem estiver sondando. O Admin, idem — é uma tela
# de login a mais, com CSRF de formulário e enumeração de modelos atrás.
#
# Quem precisar dos dois em produção liga explicitamente, e assume a escolha.
EXPOSE_ADMIN = config("EXPOSE_ADMIN", default=False, cast=bool)
EXPOSE_API_DOCS = config("EXPOSE_API_DOCS", default=False, cast=bool)

# Atrás do proxy da plataforma. Ver a nota de NUM_PROXIES em base.py: sem um
# número declarado, o limite anônimo é contornável só mandando um
# `X-Forwarded-For` diferente a cada requisição.
REST_FRAMEWORK["NUM_PROXIES"] = config("NUM_PROXIES", default=1, cast=int)  # noqa: F405

# Não vaza a URL interna (que carrega ids) para sites de terceiros.
SECURE_REFERRER_POLICY = "same-origin"

# ------------------------------------------------------------------ e-mail

# Em produção o default inverte: transporte de verdade, não console.
#
# Herdar o console aqui seria o pior dos mundos — o envio "funcionaria", os
# alertas passariam a SENT, o log encheria de e-mails bonitos e nenhum usuário
# receberia nada. Uma falha que se parece com sucesso.
#
# O default NÃO é mais SMTP. A Railway bloqueia toda porta SMTP na saída —
# testado direto no container: 587/465/25/2525 falham com "Network
# unreachable", e HTTP(S) passa normal. Nenhuma credencial de SMTP funcionaria
# aqui, de nenhum provedor. O backend do Anymail fala com o provedor por
# HTTPS, e por isso sobrevive ao bloqueio; a chave mora em `ANYMAIL` (base.py).
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="anymail.backends.brevo.EmailBackend"
)

# Conexões persistentes: o papel e a GUC do RLS são SET LOCAL, desfeitos no
# COMMIT, então reaproveitar a conexão não carrega o usuário de uma request para
# a próxima. Ver core/rls.py.
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405

# ------------------------------------------------- rastreamento de erro

# Sem DSN, nada é inicializado — e é assim que o desenvolvimento e o CI rodam.
# A ausência é o default de propósito: um SDK de APM ligado por acidente num
# ambiente de teste manda dado de verdade para um projeto de mentira.
SENTRY_DSN = config("SENTRY_DSN", default="")

if SENTRY_DSN:
    import sentry_sdk

    from core.observabilidade import opcoes_do_sentry

    # As opções moram em `core/observabilidade.py`, e não soltas aqui dentro,
    # porque ninguém consegue afirmar nada sobre uma chamada — só sobre um
    # valor. Lá elas são um dicionário, e
    # `tests/security/test_observability_redaction.py` verifica cada invariante:
    # PII desligado, corpo de requisição nunca coletado, e o mesmo `scrub` do
    # RedactingFilter aplicado no `before_send`.
    #
    # Importar `core.observabilidade` daqui é seguro: ele só puxa `core.logging`,
    # que é stdlib pura. Nada de model, nada que dependa do registry de apps —
    # que ainda não existe no momento em que este módulo é lido.
    sentry_sdk.init(
        **opcoes_do_sentry(
            SENTRY_DSN,
            # O Railway injeta o nome do ambiente; sem ele, o rótulo honesto.
            config(
                "SENTRY_ENVIRONMENT",
                default=config("RAILWAY_ENVIRONMENT_NAME", default="producao"),
            ),
            config("SENTRY_TRACES_SAMPLE_RATE", default=0.0, cast=float),
        )
    )
