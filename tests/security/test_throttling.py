"""
Limite de taxa (Phase 4).

O `django-axes` já cobria o login, por tentativa de senha. Todo o resto da API
não tinha teto nenhum — inclusive a exportação, que transmite a queryset inteira
em streaming e é, por larga margem, o endpoint mais caro do sistema.

Os testes abaixo cobrem os três eixos que dão errado calado: o limite não valer,
o limite derrubar a aplicação junto com o cache, e o limite ser contornável por
um cabeçalho que o cliente escolhe.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import SimpleRateThrottle

from core.throttling import AnonimoThrottle, UsuarioThrottle

pytestmark = pytest.mark.django_db


@contextmanager
def taxas(rates=None, **kwargs):
    """
    Ajusta taxas e demais chaves do bloco REST_FRAMEWORK durante o bloco.

    As taxas exigem `patch.object`, e não `override_settings`, e o motivo é uma
    armadilha do DRF: `SimpleRateThrottle.THROTTLE_RATES` é atributo de
    **classe**, avaliado uma única vez no import do módulo. Trocar
    `settings.REST_FRAMEWORK` recarrega `api_settings`, mas a classe continua
    apontando para o dicionário antigo — e o teste passa a medir a taxa de
    produção, silenciosamente. Foi assim que a primeira versão destes testes
    falhou: 3/hour configurado, quarta requisição devolvendo 200.

    As demais chaves (`NUM_PROXIES`) são lidas de `api_settings` no momento da
    chamada, então para elas `override_settings` funciona.
    """
    from django.conf import settings

    config = {**settings.REST_FRAMEWORK, **kwargs}
    novas_taxas = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **(rates or {})}

    with (
        override_settings(REST_FRAMEWORK=config),
        patch.object(SimpleRateThrottle, "THROTTLE_RATES", novas_taxas),
    ):
        yield


# ------------------------------------------------------------ o teto vale


def test_anonimo_leva_429_ao_passar_do_limite(api_client):
    """
    `REMOTE_ADDR` explícito, e não o 127.0.0.1 padrão do test client, porque o
    contador anônimo é por IP e ele é COMPARTILHADO com quem mais bater no
    endpoint a partir do mesmo endereço. O healthcheck do `docker-compose` faz
    exatamente isso: `curl http://localhost:8000/api/health/` a cada 10s, no
    processo do runserver, incrementando a mesma chave no mesmo Redis.

    Com o padrão, o teste falha quando o healthcheck cai dentro da sua janela —
    a terceira requisição volta 429 antes da hora. Raro o bastante para passar
    despercebido na máquina e reprovar um PR sem relação, que é a pior forma de
    teste vermelho. Medido: 7/7 verdes com o healthcheck desligado, e falha
    reproduzível com ele ligado.
    """
    ip_so_deste_teste = {"REMOTE_ADDR": "203.0.113.7"}

    with taxas(rates={"anon": "3/hour"}):
        for _ in range(3):
            assert api_client.get(reverse("core:health"), **ip_so_deste_teste).status_code == 200

        assert api_client.get(reverse("core:health"), **ip_so_deste_teste).status_code == 429


def test_usuario_autenticado_tem_teto_proprio(auth_client):
    url = reverse("tables:table-list")

    with taxas(rates={"user": "3/hour"}):
        for _ in range(3):
            assert auth_client.get(url).status_code == 200

        assert auth_client.get(url).status_code == 429


def test_o_teto_de_um_usuario_nao_afeta_o_outro(authenticate, user, other_user):
    """
    A identidade do throttle autenticado é o id do usuário, não o IP. Se fosse o
    IP, dois usuários atrás do mesmo NAT — um escritório inteiro — dividiriam a
    cota, e o sistema pareceria quebrado para quem não fez nada.
    """
    url = reverse("tables:table-list")

    with taxas(rates={"user": "2/hour"}):
        cliente = authenticate(user)
        for _ in range(2):
            assert cliente.get(url).status_code == 200
        assert cliente.get(url).status_code == 429

        assert authenticate(other_user).get(url).status_code == 200


# ------------------------------------------------- o export tem teto próprio


def test_export_esgota_antes_da_cota_geral(auth_client, table, columns):
    """
    O ponto do escopo separado: o export para de responder **sem** consumir o
    direito do usuário de continuar navegando na tabela.
    """
    export = reverse("records:record-export", args=[table.id])
    listagem = reverse("records:record-list", args=[table.id])

    with taxas(rates={"user": "100/hour", "export": "2/hour"}):
        for _ in range(2):
            assert auth_client.get(export).status_code == 200

        assert auth_client.get(export).status_code == 429
        # A navegação normal segue de pé.
        assert auth_client.get(listagem).status_code == 200


# --------------------------------------------- o cache não derruba o serviço


class CacheQuebrado:
    """
    Cache que levanta em qualquer operação — um Redis fora do ar.

    A primeira versão deste teste remendava
    `SimpleRateThrottle.get_cache_key`, e não funcionou: `AnonRateThrottle`
    **redefine** esse método, então a substituição na classe base nunca era
    alcançada, o throttle rodou de verdade e devolveu 429.

    Derrubar o próprio cache é mais fiel de qualquer forma: é onde a falha
    acontece na realidade, e cobre qualquer caminho que o DRF use para chegar
    nele.
    """

    def get(self, *args, **kwargs):
        raise ConnectionError("Redis fora do ar")

    def set(self, *args, **kwargs):
        raise ConnectionError("Redis fora do ar")


def test_cache_fora_do_ar_libera_em_vez_de_devolver_500(api_client, monkeypatch):
    """
    O motivo de `core.throttling` existir.

    Com os contadores no Redis — que é o que faz o limite valer para o conjunto
    dos workers —, um `cache.get()` que levanta subiria pela view e viraria 500
    em TODA requisição. Uma medida de proteção não pode ampliar a
    indisponibilidade que ela existe para reduzir.
    """

    monkeypatch.setattr(SimpleRateThrottle, "cache", CacheQuebrado())

    with taxas(rates={"anon": "1/hour"}):
        # 1/hora: sem o fail-open, a segunda requisição já seria 429 — ou 500,
        # se a exceção do cache subisse pela view.
        for _ in range(5):
            assert api_client.get(reverse("core:health")).status_code == 200


# ------------------------------------------ o limite não é contornável por header


def test_x_forwarded_for_forjado_nao_cria_identidade_nova():
    """
    Sem `NUM_PROXIES`, o `get_ident` do DRF usa o `X-Forwarded-For` INTEIRO como
    identidade — e quem manda um valor diferente a cada requisição vira um
    cliente novo a cada requisição. O teto anônimo deixaria de existir para
    exatamente quem tem intenção de contorná-lo.

    Com o número de proxies declarado, o DRF conta de trás para frente e pega o
    endereço que o PROXY escreveu, que o cliente não controla.
    """
    factory = APIRequestFactory()
    throttle = AnonimoThrottle()

    def ident(xff):
        pedido = factory.get("/api/health/", HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR="10.0.0.9")
        return throttle.get_ident(pedido)

    with taxas(NUM_PROXIES=1):
        # O último endereço é o que o proxy acrescentou; tudo antes veio do
        # cliente. As duas requisições têm que ser o MESMO cliente.
        assert ident("1.2.3.4, 203.0.113.7") == ident("9.9.9.9, 203.0.113.7")
        assert ident("1.2.3.4, 203.0.113.7") == "203.0.113.7"


def test_a_identidade_do_usuario_autenticado_ignora_o_ip(user):
    """Autenticado, o IP não participa — o id do usuário é a chave."""
    factory = APIRequestFactory()
    throttle = UsuarioThrottle()

    pedido = factory.get("/api/tables/", REMOTE_ADDR="10.0.0.9")
    pedido.user = user

    chave = throttle.get_cache_key(pedido, view=None)

    assert str(user.pk) in chave
    assert "10.0.0.9" not in chave
