"""
O healthcheck da plataforma, batendo como ele bate de verdade.

Escrito depois de `web` e `frontend` ficarem em 502 no primeiro deploy real
(2026-08-24), com os containers de pé. Os dois serviços em 502 eram exatamente
os dois com `healthcheck` declarado em `.railway/railway.ts`; `worker` e
`cron-alertas`, sem healthcheck, rodavam. Deploy que não passa no healthcheck
nunca entra em serviço, e o domínio responde 502.

No `web` havia DUAS causas independentes, e cada uma sozinha bastava:

  1. o healthcheck chega pela rede interna com `Host: healthcheck.railway.app`,
     que não estava em ALLOWED_HOSTS -> 400 (DisallowedHost);
  2. chega em HTTP puro, sem `X-Forwarded-Proto` -> SECURE_SSL_REDIRECT -> 301.

O CI já exercitava `/api/health/`, e passava: ele mandava `Host: localhost` (que
estava em DJANGO_ALLOWED_HOSTS) e `X-Forwarded-Proto: https`. Contornava as duas
condições, e por isso não viu nada. É essa a lacuna que este arquivo fecha —
aqui a requisição é montada SEM os dois, de propósito.

Subprocesso pelo mesmo motivo de `test_allowed_hosts.py`: `prod.py` escreve
sobre o dicionário que `base.py` exporta, e importá-lo aqui vazaria configuração
de produção para os testes seguintes.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

HOST_DO_HEALTHCHECK = "healthcheck.railway.app"
DOMINIO_PUBLICO = "web-abc.up.railway.app"

BASE_DO_AMBIENTE = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": "n7Qw2Kx9Lp4Zr8Vt6Ys1Bd3Fg5Hj0Mn7Pq2Rs4Tu6Wx8Yz1Ac3Ef5",
    "CORS_ALLOWED_ORIGINS": "https://front.up.railway.app",
    # Vazias, e não ausentes: sem a chave no ambiente o `python-decouple` cai no
    # `.env` do repositório e o teste mediria a configuração de desenvolvimento.
    "DJANGO_ALLOWED_HOSTS": "",
}

# Chama a aplicação WSGI de verdade, com a pilha de middleware inteira. Um
# RequestFactory pularia justamente o que está sendo medido.
SONDA = """
import io, json, sys

import config.wsgi

capturado = {}


def start_response(status, headers, exc_info=None):
    capturado["status"] = int(status.split()[0])
    capturado["headers"] = dict(headers)


environ = {
    "REQUEST_METHOD": "GET",
    "PATH_INFO": sys.argv[1],
    "SERVER_NAME": "localhost",
    "SERVER_PORT": "8080",
    "SERVER_PROTOCOL": "HTTP/1.1",
    "wsgi.input": io.BytesIO(b""),
    "wsgi.url_scheme": "http",
    "HTTP_HOST": sys.argv[2],
}

# O terceiro argumento é o X-Forwarded-Proto; vazio significa AUSENTE, que é
# como o healthcheck interno chega.
if len(sys.argv) > 3 and sys.argv[3]:
    environ["HTTP_X_FORWARDED_PROTO"] = sys.argv[3]

list(config.wsgi.application(environ, start_response))

print(json.dumps(capturado))
"""


def _bater(caminho: str, host: str, proto: str = "", **extra: str) -> dict:
    ambiente = {
        **os.environ,
        **BASE_DO_AMBIENTE,
        "RAILWAY_PUBLIC_DOMAIN": DOMINIO_PUBLICO,
        **extra,
    }

    resultado = subprocess.run(
        [sys.executable, "-c", SONDA, caminho, host, proto],
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return json.loads(resultado.stdout.strip().splitlines()[-1])


# ------------------------------------------------------ as duas regressões


def test_o_healthcheck_da_plataforma_nao_leva_400():
    """
    Causa 1: o Host da rede interna não é o domínio público.

    Um 400 aqui é o `DisallowedHost` — e o efeito prático dele não é um erro
    visível, é o deploy inteiro reprovado.
    """
    resposta = _bater("/api/health/", HOST_DO_HEALTHCHECK)

    assert resposta["status"] != 400, (
        f"{HOST_DO_HEALTHCHECK} foi recusado: o deploy reprovaria e o domínio "
        "responderia 502"
    )


def test_o_healthcheck_da_plataforma_nao_leva_301():
    """
    Causa 2: sem `X-Forwarded-Proto`, o SECURE_SSL_REDIRECT dispara.

    Este é o teste que o CI não tinha: lá o header ia junto, e o 301 nunca
    aparecia.
    """
    resposta = _bater("/api/health/", HOST_DO_HEALTHCHECK)

    assert resposta["status"] not in (301, 302), (
        "o health respondeu redirect para o healthcheck interno; "
        f"Location={resposta['headers'].get('Location')!r}"
    )


def test_a_requisicao_chega_na_view():
    """
    As duas anteriores medem o que NÃO acontece. Esta mede o que acontece: a
    requisição atravessa a pilha e a view responde.

    200 com o banco de pé, 503 sem ele — as duas provam que passou dos
    middlewares, que é o que estava quebrado.
    """
    resposta = _bater("/api/health/", HOST_DO_HEALTHCHECK)

    assert resposta["status"] in (200, 503), (
        f"a view não foi alcançada (status {resposta['status']})"
    )


# ------------------------------------------------- o que NÃO pode ter afrouxado


def test_o_resto_da_aplicacao_continua_redirecionando():
    """
    A isenção do SSL redirect vale para um caminho, não para o serviço.

    A correção fácil para o 301 do healthcheck é desligar o SECURE_SSL_REDIRECT
    inteiro — foi o que resolveu o problema na maioria dos relatos, e derruba a
    garantia de HTTPS de toda a aplicação por causa de um endpoint. Se alguém
    fizer isso, este teste é quem reclama.
    """
    resposta = _bater("/api/auth/login/", DOMINIO_PUBLICO)

    assert resposta["status"] in (301, 302), (
        "uma rota comum em HTTP puro não redirecionou — o SECURE_SSL_REDIRECT "
        "foi desligado ou isentado além do health"
    )
    assert resposta["headers"]["Location"].startswith("https://")


def test_sem_host_configurado_o_healthcheck_nao_entra_sozinho():
    """
    Aceitar um Host que não é nosso tem custo, e o custo fica contido.

    A condição de entrada é ter ALGUM host configurado. A primeira versão desta
    correção dependia de `RAILWAY_PUBLIC_DOMAIN`, e era frágil de um jeito ruim:
    se a plataforma não injetasse essa variável, a correção não fazia nada — sem
    erro, sem log, indistinguível de não ter sido aplicada.

    O que continua garantido é o outro lado: com a lista vazia, que é o caso de
    desenvolvimento, o nome não entra por conta própria e a lista segue vazia.
    """
    resultado = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, django;"
            "django.setup();"
            "from django.conf import settings as s;"
            "print(json.dumps(list(s.ALLOWED_HOSTS)))",
        ],
        cwd=BASE_DIR,
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.dev",
            "DJANGO_ALLOWED_HOSTS": "",
            "RAILWAY_PUBLIC_DOMAIN": "",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    hosts = json.loads(resultado.stdout.strip().splitlines()[-1])

    assert hosts == [], f"a lista deveria seguir vazia, veio {hosts!r}"
