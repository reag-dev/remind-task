"""
Validação da superfície HTTP, no momento em que ela existe.

Estas checagens moravam em `config/settings/prod.py`, no corpo do módulo. O
efeito era que **todo processo que carregasse as settings** as executava — e o
Celery carrega. Um worker, que não atende requisição nenhuma, se recusava a
subir por não ter uma lista de origens CORS. Aconteceu duas vezes no primeiro
deploy real (2026-08-24): primeiro `ALLOWED_HOSTS`, depois `CORS_ALLOWED_ORIGINS`.

Corrigir declarando as variáveis nos serviços sem HTTP resolvia o sintoma e
deixava a armadilha montada: a próxima guarda acrescentada a `prod.py` voltaria
a derrubar o worker, com uma mensagem sobre um conceito que não se aplica a ele.

O gatilho certo é o carregamento do WSGI. `config/wsgi.py` é importado pelo
gunicorn e pelo `runserver` (via `WSGI_APPLICATION`), e por mais ninguém —
`config/celery.py` não o importa, e nem os comandos de `manage.py`. Então
chamar daqui preserva a propriedade que interessa (o serviço web se recusa a
subir mal configurado, no boot) e elimina o alarme falso em quem não serve.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SAMESITE_VALIDOS = frozenset({"Lax", "Strict", "None"})


def validar_superficie_http() -> None:
    """
    Levanta `ImproperlyConfigured` se a configuração HTTP não fecha.

    Não faz nada quando `VALIDAR_SUPERFICIE_HTTP` é falso, que é o caso de
    desenvolvimento: ali `ALLOWED_HOSTS` e CORS vazios são um começo legítimo, e
    quebrar o `runserver` por isso só atrapalha.
    """
    if not getattr(settings, "VALIDAR_SUPERFICIE_HTTP", False):
        return

    # Sem host declarado o Django recusa tudo com 400 e ninguém entende por quê.
    if not settings.ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS é obrigatório em produção. Em plataformas "
            "como o Railway, o serviço com domínio público o recebe pronto em "
            "RAILWAY_PUBLIC_DOMAIN (ver base.py); os demais precisam da "
            "variável declarada."
        )

    # CORS vazio com credenciais ligadas é pior que host vazio: a SPA fica em
    # branco com erro só no console, e a "correção" tentadora é
    # CORS_ALLOW_ALL_ORIGINS — que com cookie é grave.
    if not settings.CORS_ALLOWED_ORIGINS:
        raise ImproperlyConfigured(
            "CORS_ALLOWED_ORIGINS é obrigatório em produção: o frontend está "
            "em outra origem e nenhuma chamada da SPA passaria."
        )

    samesite = settings.AUTH_COOKIE_SAMESITE

    # Um valor inválido não é recusado pelo Django: vira atributo de cookie que
    # o browser ignora, de volta ao comportamento padrão, em silêncio.
    if samesite not in SAMESITE_VALIDOS:
        raise ImproperlyConfigured(
            f"AUTH_COOKIE_SAMESITE={samesite!r} não é válido; "
            f"use um de {sorted(SAMESITE_VALIDOS)}."
        )

    # `None` sem `Secure` é a combinação que o browser descarta **sem avisar**:
    # o cookie não é recusado com erro, ele só nunca chega, e o sintoma é a
    # sessão morrendo a cada 15 minutos.
    if samesite == "None" and not settings.AUTH_COOKIE_SECURE:
        raise ImproperlyConfigured(
            "AUTH_COOKIE_SAMESITE='None' exige AUTH_COOKIE_SECURE=True; sem "
            "Secure o browser descarta o cookie sem avisar."
        )
