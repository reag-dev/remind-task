"""
Critério 6 da seção 10 — "dados trafegam via HTTPS em produção" (RS06).

Os dois testes rodam `config.settings.prod` num **subprocesso**. Importar o
módulo aqui dentro seria mais rápido e estaria errado: `prod.py` faz
`DATABASES["default"][...] = ...` sobre o mesmo dicionário que `base.py` exporta
— o objeto que a sessão de teste está usando. A configuração de produção
vazaria para os testes seguintes, e a ordem de execução decidiria o resultado.

O subprocesso também é mais fiel: é literalmente o comando que se roda antes de
publicar.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]

# Chave forte de mentira: o `check --deploy` reprova SECRET_KEY curta ou pouco
# variada (W009), e a do ambiente de teste é fraca de propósito.
AMBIENTE_DE_PRODUCAO = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": "n7Qw2Kx9Lp4Zr8Vt6Ys1Bd3Fg5Hj0Mn7Pq2Rs4Tu6Wx8Yz1Ac3Ef5",
    "DJANGO_ALLOWED_HOSTS": "remind.example.com",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
}


def _run(*args: str) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **AMBIENTE_DE_PRODUCAO}
    return subprocess.run(
        [sys.executable, *args],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_production_settings_pass_djangos_own_deployment_checks():
    """
    `--fail-level WARNING` é o que dá dente ao teste.

    Sem ele o `check --deploy` sai com código 0 mesmo listando os avisos, e o
    teste passaria com HSTS desligado, cookie sem Secure e DEBUG ligado.
    """
    resultado = _run("manage.py", "check", "--deploy", "--fail-level", "WARNING")

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


@pytest.mark.parametrize(
    "chave, esperado",
    [
        ("DEBUG", False),
        ("SECURE_SSL_REDIRECT", True),
        ("SECURE_HSTS_INCLUDE_SUBDOMAINS", True),
        ("SECURE_HSTS_PRELOAD", True),
        ("SECURE_CONTENT_TYPE_NOSNIFF", True),
        ("SESSION_COOKIE_SECURE", True),
        ("SESSION_COOKIE_HTTPONLY", True),
        ("CSRF_COOKIE_SECURE", True),
        ("AUTH_COOKIE_SECURE", True),
        ("AUTH_COOKIE_HTTPONLY", True),
    ],
)
def test_production_forces_https_and_locks_the_cookies(producao, chave, esperado):
    assert producao[chave] is esperado, f"{chave} deveria ser {esperado} em produção"


def test_hsts_lasts_at_least_a_year(producao):
    """Menos de um ano não é aceito por nenhuma lista de preload."""
    assert producao["SECURE_HSTS_SECONDS"] >= 31_536_000


def test_the_browsable_api_is_off_in_production(producao):
    """
    O renderer navegável monta formulário HTML a partir do serializer.

    Em produção isso é superfície de ataque sem contrapartida: acrescenta
    template, CSRF de formulário e uma UI que ninguém usa.
    """
    assert producao["RENDERERS"] == ["rest_framework.renderers.JSONRenderer"]


@pytest.fixture(scope="module")
def producao():
    """Valores efetivos de `config.settings.prod`, lidos de fora do processo."""
    resultado = _run(
        "-c",
        "import json, django; django.setup();"
        "from django.conf import settings as s;"
        "print(json.dumps({"
        "  'DEBUG': s.DEBUG,"
        "  'SECURE_SSL_REDIRECT': s.SECURE_SSL_REDIRECT,"
        "  'SECURE_HSTS_SECONDS': s.SECURE_HSTS_SECONDS,"
        "  'SECURE_HSTS_INCLUDE_SUBDOMAINS': s.SECURE_HSTS_INCLUDE_SUBDOMAINS,"
        "  'SECURE_HSTS_PRELOAD': s.SECURE_HSTS_PRELOAD,"
        "  'SECURE_CONTENT_TYPE_NOSNIFF': s.SECURE_CONTENT_TYPE_NOSNIFF,"
        "  'SESSION_COOKIE_SECURE': s.SESSION_COOKIE_SECURE,"
        "  'SESSION_COOKIE_HTTPONLY': s.SESSION_COOKIE_HTTPONLY,"
        "  'CSRF_COOKIE_SECURE': s.CSRF_COOKIE_SECURE,"
        "  'AUTH_COOKIE_SECURE': s.AUTH_COOKIE_SECURE,"
        "  'AUTH_COOKIE_HTTPONLY': s.AUTH_COOKIE_HTTPONLY,"
        "  'CSRF_TRUSTED_ORIGINS': s.CSRF_TRUSTED_ORIGINS,"
        "  'RENDERERS': list(s.REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES']),"
        "}))",
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return json.loads(resultado.stdout.strip().splitlines()[-1])


def test_csrf_trusted_origins_are_https_and_well_formed(producao):
    """
    `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` não usam a mesma notação, e um
    valor malformado não é recusado no boot — ele só nunca casa, e todo POST
    por sessão vira 403.
    """
    origens = producao["CSRF_TRUSTED_ORIGINS"]

    assert origens == ["https://remind.example.com"]
    assert all(origem.startswith("https://") for origem in origens)
    assert not any(origem.startswith("https://.") for origem in origens)
