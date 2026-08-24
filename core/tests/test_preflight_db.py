"""
O comando que decide se `migrate` pode rodar.

Um preflight que passa quando não deveria é pior do que não existir: ele dá
permissão para a sequência de migrations quebrar no meio, com a autoridade de
ter sido "verificado". Por isso os testes aqui olham as duas pontas — que ele
aprova um banco apto, e que ele REPROVA e sai com código != 0 quando uma
checagem obrigatória falha.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection

from core.management.commands import preflight_db

pytestmark = pytest.mark.django_db


def rodar():
    saida = StringIO()
    call_command("preflight_db", stdout=saida)
    return saida.getvalue()


def test_aprova_o_banco_da_suite():
    """
    O Postgres do compose é o mesmo do CI, e satisfaz tudo que as migrations
    exigem — se não satisfizesse, a suíte inteira não rodaria.
    """
    saida = rodar()

    assert "Banco apto" in saida
    assert "FALHOU" not in saida
    assert "ERRO" not in saida


def test_verifica_o_que_a_migration_de_rls_precisa():
    saida = rodar()

    for checagem in ("CREATE ROLE", "GRANT do papel", "RLS aplicavel", "ICU"):
        assert checagem in saida, f"o preflight deixou de checar {checagem!r}"


def test_nao_deixa_nada_para_tras():
    """
    O comando cria papel, collation, tabela e policy para descobrir se consegue.
    Tudo dentro de transação que termina em ROLLBACK — senão o próprio preflight
    viraria a sujeira que ele deveria evitar, e rodá-lo duas vezes falharia na
    segunda por objeto já existente.
    """
    rodar()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", [preflight_db.ROLE_DE_TESTE]
        )
        assert cursor.fetchone() is None, "o papel de teste sobreviveu"

        cursor.execute("SELECT 1 FROM pg_collation WHERE collname = 'preflight_icu'")
        assert cursor.fetchone() is None, "a collation de teste sobreviveu"

        cursor.execute("SELECT to_regclass('preflight_rls')")
        assert cursor.fetchone()[0] is None, "a tabela de teste sobreviveu"


def test_pode_rodar_duas_vezes():
    """Corolário do anterior, e o uso real: quem roda, roda de novo."""
    rodar()
    assert "Banco apto" in rodar()


def test_reprova_com_codigo_de_saida_quando_uma_checagem_falha(monkeypatch):
    """
    O ponto do teste: reprovar **e** sair diferente de zero.

    Sem o código de saída, o comando serviria para leitura humana e seria
    inútil como gate de pipeline — um `railway run ... && migrate` seguiria em
    frente depois de reprovar.
    """

    def sem_create_role(self):
        raise preflight_db.Falha("o usuario nao tem CREATEROLE")

    monkeypatch.setattr(preflight_db.Command, "_create_role", sem_create_role)

    saida = StringIO()
    with pytest.raises(SystemExit) as saiu:
        call_command("preflight_db", stdout=saida)

    assert saiu.value.code == 1
    assert "FALHOU" in saida.getvalue()
    assert "NAO rode `migrate`" in saida.getvalue()
    assert "Banco apto" not in saida.getvalue()


def test_erro_inesperado_tambem_reprova(monkeypatch):
    """
    Uma checagem pode explodir de um jeito que ninguém previu — permissão
    negada, sintaxe recusada por um fork do Postgres. Isso é reprovação, não
    exceção não tratada: um traceback no meio do deploy não diz o que fazer.
    """

    def explode(self):
        raise RuntimeError("algo bem estranho")

    monkeypatch.setattr(preflight_db.Command, "_icu", explode)

    saida = StringIO()
    with pytest.raises(SystemExit):
        call_command("preflight_db", stdout=saida)

    assert "ERRO" in saida.getvalue()
    assert "RuntimeError" in saida.getvalue()


def test_extensoes_sao_informativas_e_nao_reprovam(monkeypatch):
    """
    O plano supunha que `citext` e `pgcrypto` fossem requisito. Medido: nenhuma
    das duas é usada — o e-mail case-insensitive virou collation ICU quando o
    Django 5.1 removeu `CIEmailField`, e os UUIDs vêm de `uuid.uuid4`. Ausência
    delas não pode bloquear deploy nenhum.
    """
    monkeypatch.setattr(
        preflight_db.Command, "_extensao_disponivel", lambda self, nome: False
    )

    saida = rodar()

    assert "Banco apto" in saida
    assert "nao usada pela aplicacao" in saida
