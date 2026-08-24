"""
Como `ALLOWED_HOSTS` se preenche em produção — e o que acontece quando não se
preenche.

Escrito depois de derrubar o `worker` no primeiro deploy real (2026-08-24). O
`web` subiu e o `worker` não, com o mesmo módulo de settings e o mesmo código: a
diferença é que só o serviço com domínio público recebe `RAILWAY_PUBLIC_DOMAIN`,
e era ele que estava preenchendo a lista sozinho. Nada testava esse mecanismo,
então a assimetria só apareceu em produção.

Como em `test_transport.py`, tudo roda em subprocesso: `prod.py` escreve sobre o
mesmo dicionário que `base.py` exporta, e importá-lo aqui vazaria configuração
de produção para os testes seguintes.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

# Sem DJANGO_ALLOWED_HOSTS nem RAILWAY_PUBLIC_DOMAIN — cada teste acrescenta o
# que quer medir.
BASE_DO_AMBIENTE = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": "n7Qw2Kx9Lp4Zr8Vt6Ys1Bd3Fg5Hj0Mn7Pq2Rs4Tu6Wx8Yz1Ac3Ef5",
    "CORS_ALLOWED_ORIGINS": "https://front.up.railway.app",
}

# Vazias, e não ausentes — a diferença importa.
#
# O `python-decouple` procura a variável no ambiente e, **não achando**, cai no
# arquivo `.env` do repositório, que declara `DJANGO_ALLOWED_HOSTS`. Remover a
# chave do `os.environ` não esvazia coisa nenhuma: só passa a leitura para o
# arquivo, e o teste mediria a configuração de desenvolvimento achando que
# mediu a ausência. Declarada como string vazia, o ambiente vence.
VAZIAS = {"DJANGO_ALLOWED_HOSTS": "", "RAILWAY_PUBLIC_DOMAIN": ""}

# Entra na lista junto com o domínio público, e por isso aparece nas asserções
# abaixo: é o Host com que a plataforma bate no healthcheck pela rede interna.
# Ver tests/security/test_healthcheck_plataforma.py, que mede o porquê — aqui só
# se mede a composição da lista.
#
# As asserções continuam sobre a lista INTEIRA de propósito: foi a igualdade
# exata que denunciou este acréscimo, em vez de deixá-lo passar despercebido.
HOST_DO_HEALTHCHECK = "healthcheck.railway.app"


def _carregar(**extra: str) -> subprocess.CompletedProcess:
    ambiente = {**os.environ, **VAZIAS, **BASE_DO_AMBIENTE, **extra}

    return subprocess.run(
        [
            sys.executable,
            "-c",
            # `config.wsgi`, e não só `django.setup()`: é ele que dispara as
            # guardas de superfície HTTP (ver config/validacao.py). Importar só
            # as settings mediria um caminho que não valida mais nada — e é
            # exatamente o caminho do worker do Celery.
            "import json, config.wsgi;"
            "from django.conf import settings as s;"
            "print(json.dumps({'ALLOWED_HOSTS': list(s.ALLOWED_HOSTS)}))",
        ],
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _hosts(resultado: subprocess.CompletedProcess) -> list[str]:
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return json.loads(resultado.stdout.strip().splitlines()[-1])["ALLOWED_HOSTS"]


def test_sem_host_nenhum_o_boot_falha():
    """A guarda em si. Sem host declarado o Django recusaria tudo com 400."""
    resultado = _carregar()

    assert resultado.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in resultado.stderr


def test_o_dominio_da_plataforma_sozinho_ja_satisfaz():
    """
    É isto que faz o serviço `web` subir sem ninguém declarar a variável — e,
    por tabela, o que escondeu a falta dela nos serviços sem domínio.
    """
    resultado = _carregar(RAILWAY_PUBLIC_DOMAIN="web-abc.up.railway.app")

    assert _hosts(resultado) == ["web-abc.up.railway.app", HOST_DO_HEALTHCHECK]


def test_a_variavel_sozinha_tambem_satisfaz():
    """O caminho de quem não está no Railway, ou tem domínio próprio."""
    resultado = _carregar(DJANGO_ALLOWED_HOSTS="api.exemplo.com")

    assert _hosts(resultado) == ["api.exemplo.com", HOST_DO_HEALTHCHECK]


def test_os_dois_convivem_sem_duplicar():
    resultado = _carregar(
        DJANGO_ALLOWED_HOSTS="api.exemplo.com",
        RAILWAY_PUBLIC_DOMAIN="web-abc.up.railway.app",
    )

    hosts = _hosts(resultado)

    assert hosts == ["api.exemplo.com", "web-abc.up.railway.app", HOST_DO_HEALTHCHECK]
    assert len(hosts) == len(set(hosts))


def test_dominio_ja_declarado_nao_entra_duas_vezes():
    resultado = _carregar(
        DJANGO_ALLOWED_HOSTS="web-abc.up.railway.app",
        RAILWAY_PUBLIC_DOMAIN="web-abc.up.railway.app",
    )

    assert _hosts(resultado) == ["web-abc.up.railway.app", HOST_DO_HEALTHCHECK]


def test_a_mensagem_aponta_de_onde_o_valor_deveria_vir():
    """
    Quem lê esta mensagem está olhando um traceback longo e precisa saber o que
    fazer, não só o que faltou.

    A versão anterior deste teste exigia que a mensagem explicasse o caso do
    worker do Celery. Deixou de fazer sentido quando as guardas saíram do corpo
    das settings: o worker não carrega mais o WSGI, então nunca vê esta
    mensagem. O que sobra é apontar o mecanismo da plataforma.
    """
    resultado = _carregar()

    for pista in ("RAILWAY_PUBLIC_DOMAIN", "domínio"):
        assert pista in resultado.stderr, f"a mensagem não menciona {pista!r}"


# ------------------------------------------------ o caminho sem HTTP


def test_processo_sem_http_nao_exige_nada_disso():
    """
    A regressão que custou dois deploys.

    O Celery carrega as settings, mas não importa `config.wsgi` — ele não atende
    requisição nenhuma. Enquanto as guardas moravam no corpo de `prod.py`, o
    worker se recusava a subir por falta de `ALLOWED_HOSTS`, e depois por falta
    de `CORS_ALLOWED_ORIGINS`: conceitos que não se aplicam a ele.

    Este teste percorre o mesmo caminho do worker — `config.celery`, sem WSGI —
    com o ambiente pelado. Ele tem que subir.
    """
    resultado = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.celery; print(config.celery.app.main)",
        ],
        cwd=BASE_DIR,
        env={**os.environ, **VAZIAS, **BASE_DO_AMBIENTE, "CORS_ALLOWED_ORIGINS": ""},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert resultado.returncode == 0, (
        "o caminho do worker voltou a exigir configuração de HTTP: "
        + resultado.stdout
        + resultado.stderr
    )
    assert "remind_task" in resultado.stdout
