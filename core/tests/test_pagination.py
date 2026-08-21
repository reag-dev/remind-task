"""
Paginação com `?page_size=` e o teto que a torna segura.

A classe existe porque o `PageNumberPagination` padrão **ignora** o parâmetro em
silêncio quando `page_size_query_param` não está definido — e falha silenciosa é
o que este projeto persegue em toda camada. Ver `core/pagination.py`.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from core.pagination import PaginacaoPadrao
from records.models import Record

pytestmark = pytest.mark.django_db


BASE = date(2026, 9, 1)


def _criar_registros(table, quantidade, valid_row):
    """
    Registros com vencimentos distintos, para a ordenação ser determinística.

    Datas por `timedelta`, não por `f"2026-09-{dia:02d}"`: a segunda forma
    produz 31/09 assim que a quantidade passa de 30, e o teste morre num erro de
    validação que não tem nada a ver com paginação.
    """
    Record.objects.bulk_create(
        [
            Record(
                table=table,
                user=table.user,
                data={
                    **valid_row,
                    "data_de_vencimento": (BASE + timedelta(days=i)).isoformat(),
                },
                due_date=BASE + timedelta(days=i),
            )
            for i in range(quantidade)
        ]
    )


def test_o_teto_e_200():
    """
    O valor, fixado como literal.

    O teste abaixo prova que o teto é *aplicado*, mas deriva a expectativa da
    própria constante — então continuaria verde com `max_page_size = 50000`, que
    é exatamente a regressão a impedir. Aumentar o teto tem de ser uma decisão
    deliberada que aparece no diff, não um número que alguém dobra sem
    perceber o que ele protege.
    """
    assert PaginacaoPadrao.max_page_size == 200
    assert PaginacaoPadrao.page_size_query_param == "page_size"


def test_o_teto_de_page_size_e_aplicado(auth_client, table, columns, valid_row):
    """
    O teste que justifica a existência de `max_page_size`.

    Sem ele, `?page_size=100000` vira varredura de tabela — e cada linha carrega
    o `data` JSONB inteiro, onde moram os valores das colunas `is_sensitive`.
    Uma requisição transferiria a base toda do usuário, com o custo no servidor.
    """
    # Acima do teto de propósito: com menos de 200 registros o corte nunca
    # aconteceria e o teste passaria mesmo sem `max_page_size` definido.
    _criar_registros(table, PaginacaoPadrao.max_page_size + 5, valid_row)
    url = reverse("records:record-list", args=[table.id])

    response = auth_client.get(url, {"page_size": 100000})

    assert response.status_code == 200
    assert len(response.data["results"]) == PaginacaoPadrao.max_page_size
    assert response.data["count"] == PaginacaoPadrao.max_page_size + 5
    # Sobrou página: o resto continua acessível, só não numa tacada só.
    assert response.data["next"] is not None


def test_page_size_menor_que_o_teto_e_respeitado(auth_client, table, columns, valid_row):
    _criar_registros(table, 12, valid_row)
    url = reverse("records:record-list", args=[table.id])

    response = auth_client.get(url, {"page_size": 5})

    assert len(response.data["results"]) == 5
    assert response.data["count"] == 12
    assert response.data["next"] is not None


def test_page_size_ausente_usa_o_padrao(auth_client, table, columns, valid_row):
    _criar_registros(table, 60, valid_row)
    url = reverse("records:record-list", args=[table.id])

    response = auth_client.get(url)

    assert len(response.data["results"]) == 50
    assert response.data["count"] == 60


def test_a_segunda_pagina_traz_o_resto(auth_client, table, columns, valid_row):
    _criar_registros(table, 12, valid_row)
    url = reverse("records:record-list", args=[table.id])

    primeira = auth_client.get(url, {"page_size": 10})
    segunda = auth_client.get(url, {"page": 2, "page_size": 10})

    assert len(segunda.data["results"]) == 2
    # Nenhum registro repetido entre páginas: a ordenação padrão
    # (`due_date`, `created_at`) tem desempate, então o corte é estável.
    ids_primeira = {item["id"] for item in primeira.data["results"]}
    ids_segunda = {item["id"] for item in segunda.data["results"]}
    assert ids_primeira.isdisjoint(ids_segunda)
    assert len(ids_primeira | ids_segunda) == 12


def test_pagina_fora_do_intervalo_responde_404(auth_client, table, columns, valid_row):
    """
    Não é lista vazia — é 404, o mesmo do recurso inexistente.

    O cliente precisa distinguir os dois: "acabaram os registros" pede voltar
    para a página 1; "tabela não existe" pede sair da tela. Registrado aqui
    porque a interface depende deste comportamento.
    """
    _criar_registros(table, 3, valid_row)
    url = reverse("records:record-list", args=[table.id])

    response = auth_client.get(url, {"page": 99})

    assert response.status_code == 404


def test_a_paginacao_vale_para_tabelas_e_alertas(auth_client, user):
    """
    A classe é o padrão do projeto, não um ajuste do endpoint de registros.

    Se alguém trocar `DEFAULT_PAGINATION_CLASS` de volta, o seletor de linhas
    por página some sem aviso em três telas de uma vez.
    """
    from tables.models import Table

    Table.objects.bulk_create(
        [Table(user=user, name=f"Tabela {i}") for i in range(8)]
    )

    tabelas = auth_client.get(reverse("tables:table-list"), {"page_size": 3})
    alertas = auth_client.get(reverse("alerts:alert-list"), {"page_size": 3})

    assert len(tabelas.data["results"]) == 3
    assert tabelas.data["count"] == 8
    assert alertas.status_code == 200


def test_page_size_aparece_no_schema(auth_client):
    """
    Sem isto o parâmetro existiria mas não seria descoberto: o schema é o que
    gera os tipos do cliente (`npm run api:types`) e o que `/api/docs/` mostra.
    """
    response = auth_client.get(reverse("schema"), {"format": "json"})

    caminho = response.data["paths"]["/api/tables/{table_id}/records/"]["get"]
    nomes = {parametro["name"] for parametro in caminho["parameters"]}

    assert "page_size" in nomes
    assert "page" in nomes
