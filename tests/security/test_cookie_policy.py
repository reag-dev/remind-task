"""
A Phase 0 do plano de produção escolheu `*.up.railway.app` para os dois
serviços. `up.railway.app` está na Public Suffix List, então
`web-xxxx.up.railway.app` e `front-yyyy.up.railway.app` são **registrable
domains diferentes** — não é o caso "mesmo site" que o `SameSite=Lax` cobre.

Daí este arquivo. O modo de falha aqui não é uma exceção: é silêncio. Um cookie
`SameSite=None` sem `Secure` é descartado pelo browser sem erro, sem log e sem
aviso no console; a sessão só morre a cada 15 minutos e o usuário cai no login.
Nada em teste de integração pega isso, porque o servidor de teste não é um
browser e aceita o cookie normalmente.

Como em `test_transport.py`, tudo roda em **subprocesso**: `prod.py` escreve
sobre o mesmo dicionário `DATABASES` que `base.py` exporta, então importá-lo no
processo do pytest vazaria configuração de produção para os testes seguintes.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]

AMBIENTE_DE_PRODUCAO = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": "n7Qw2Kx9Lp4Zr8Vt6Ys1Bd3Fg5Hj0Mn7Pq2Rs4Tu6Wx8Yz1Ac3Ef5",
    "DJANGO_ALLOWED_HOSTS": "web-teste.up.railway.app",
    "CORS_ALLOWED_ORIGINS": "https://front-teste.up.railway.app",
}


def _settings(**extra: str) -> subprocess.CompletedProcess:
    """Carrega as settings num processo limpo, com o ambiente pedido."""
    env = {**os.environ, **AMBIENTE_DE_PRODUCAO, **extra}
    return subprocess.run(
        [
            sys.executable,
            "-c",
            # `config.wsgi` dispara as guardas de superfície HTTP; só
            # `django.setup()` não dispara mais nenhuma. Ver config/validacao.py.
            "import json, config.wsgi;"
            "from django.conf import settings as s;"
            "print(json.dumps({"
            "  'AUTH_COOKIE_SAMESITE': s.AUTH_COOKIE_SAMESITE,"
            "  'AUTH_COOKIE_SECURE': s.AUTH_COOKIE_SECURE,"
            "  'AUTH_COOKIE_HTTPONLY': s.AUTH_COOKIE_HTTPONLY,"
            "  'CSRF_TRUSTED_ORIGINS': s.CSRF_TRUSTED_ORIGINS,"
            "  'CORS_ALLOWED_ORIGINS': s.CORS_ALLOWED_ORIGINS,"
            "  'CORS_ALLOW_CREDENTIALS': s.CORS_ALLOW_CREDENTIALS,"
            "  'ATOMIC_REQUESTS': s.DATABASES['default']['ATOMIC_REQUESTS'],"
            "  'DB_NAME': s.DATABASES['default']['NAME'],"
            "}))",
        ],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def producao() -> dict:
    resultado = _settings()
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return json.loads(resultado.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------- o cookie


def test_o_cookie_de_refresh_atravessa_origens_diferentes(producao):
    """Com serviços em registrable domains distintos, `Lax` não serve."""
    assert producao["AUTH_COOKIE_SAMESITE"] == "None"


def test_samesite_none_vem_acompanhado_de_secure(producao):
    """A dupla que o browser exige — e descarta em silêncio se faltar."""
    assert producao["AUTH_COOKIE_SECURE"] is True
    assert producao["AUTH_COOKIE_HTTPONLY"] is True


def test_samesite_none_sem_secure_quebra_no_boot():
    """
    O teste central deste arquivo.

    Sem a guarda, esta combinação sobe um serviço aparentemente saudável cuja
    sessão expira a cada refresh. Falhar no boot troca um bug intermitente de
    produção por um container que não sobe.
    """
    resultado = _settings(AUTH_COOKIE_SECURE="False")

    assert resultado.returncode != 0, (
        "settings carregaram com SameSite=None sem Secure — a guarda sumiu"
    )
    assert "AUTH_COOKIE_SECURE" in resultado.stderr


def test_samesite_invalido_quebra_no_boot():
    """
    `SameSite=Nenhum` (ou `none`, ou um typo) não é recusado pelo Django: vira
    atributo de cookie que o browser ignora, de volta ao comportamento padrão.
    """
    resultado = _settings(AUTH_COOKIE_SAMESITE="Nenhum")

    assert resultado.returncode != 0
    assert "AUTH_COOKIE_SAMESITE" in resultado.stderr


def test_lax_continua_possivel_sem_disparar_a_guarda():
    """
    A guarda é sobre a combinação, não sobre `None`. Se um dia o projeto ganhar
    domínio próprio, voltar para `Lax` tem que ser uma variável de ambiente — e
    não um patch neste arquivo.
    """
    resultado = _settings(AUTH_COOKIE_SAMESITE="Lax")

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


# ----------------------------------------------------- as origens cruzadas


def test_o_frontend_e_origem_confiavel_para_csrf(producao):
    """
    Com front e back em domínios distintos, a derivação a partir de
    ALLOWED_HOSTS não alcança o frontend — a origem entra explicitamente.
    """
    assert "https://front-teste.up.railway.app" in producao["CORS_ALLOWED_ORIGINS"]
    assert producao["CORS_ALLOW_CREDENTIALS"] is True


def test_cors_vazio_quebra_no_boot():
    """
    Sem origem declarada nenhuma chamada da SPA passa. O modo de falha é um
    frontend em branco com erro só no console do browser — e a "correção"
    tentadora é `CORS_ALLOW_ALL_ORIGINS`, que com credenciais é grave.
    """
    resultado = _settings(CORS_ALLOWED_ORIGINS="")

    assert resultado.returncode != 0
    assert "CORS_ALLOWED_ORIGINS" in resultado.stderr


# ------------------------------------------------------- DATABASE_URL x RLS


def test_database_url_e_lida_como_fonte_primaria():
    """O Railway injeta DATABASE_URL; os POSTGRES_* são o caminho do compose."""
    resultado = _settings(
        DATABASE_URL="postgres://u:p@db.example.com:5432/banco_da_url"
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert json.loads(resultado.stdout.strip().splitlines()[-1])["DB_NAME"] == (
        "banco_da_url"
    )


@pytest.mark.parametrize(
    "fonte, extra",
    [
        ("POSTGRES_*", {}),
        ("DATABASE_URL", {"DATABASE_URL": "postgres://u:p@h:5432/b"}),
    ],
)
def test_atomic_requests_sobrevive_a_qualquer_fonte_de_configuracao(fonte, extra):
    """
    RS01 depende disto e falha **em runtime**, não no boot.

    A GUC `app.user_id` é aplicada com `SET LOCAL`, que só vale dentro de uma
    transação. Sem ATOMIC_REQUESTS o `SET LOCAL` morre no autocommit e a RLS
    deixa de isolar — sobra a camada de queryset, que é exatamente a situação
    que `test_queryset_layer.py` existe para impedir.

    `dj_database_url.parse()` devolve um dicionário novo, então qualquer refator
    que volte a escrever `DATABASES['default'] = parse(...)` apaga a chave sem
    que nada mais reclame.
    """
    resultado = _settings(**extra)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    dados = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert dados["ATOMIC_REQUESTS"] is True, (
        f"ATOMIC_REQUESTS perdido quando a config vem de {fonte} — RLS quebrada"
    )
