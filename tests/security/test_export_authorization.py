"""
Critério 8 da seção 10 — "exportação CSV exige autenticação e autorização" (RS08).

A exportação é o ponto onde um vazamento é mais caro: não devolve um registro,
devolve a tabela inteira num arquivo que sai do sistema e vira anexo de e-mail.

A defesa não é uma checagem a mais — é a AUSÊNCIA de um caminho de consulta
próprio. O endpoint é uma action do `RecordViewSet` e usa o mesmo
`get_queryset()` e o mesmo `filter_queryset()` da listagem. Uma view separada
seria um segundo lugar onde esquecer o filtro por dono.

A neutralização de fórmula no CSV (a outra metade de RS08) tem suíte própria em
`exports/tests/test_export.py`.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def baixar(client, table_id, **params):
    resposta = client.get(reverse("records:record-export", args=[table_id]), params)
    corpo = b"".join(resposta.streaming_content).decode("utf-8")
    return resposta, corpo


def test_the_export_refuses_an_anonymous_request(api_client, mine):
    resposta = api_client.get(reverse("records:record-export", args=[mine.table.id]))

    assert resposta.status_code == 401
    assert not hasattr(resposta, "streaming_content"), "não pode começar a escrever o CSV"


def test_the_export_of_a_foreign_table_is_a_404(auth_client, theirs):
    resposta = auth_client.get(reverse("records:record-export", args=[theirs.table.id]))

    assert resposta.status_code == 404


def test_the_owner_gets_only_their_own_rows(auth_client, mine, theirs):
    """
    B tem tabela, coluna e registro de forma idêntica. Se o export usasse uma
    consulta própria — por `table_id` sem dono, digamos — este teste ainda
    passaria; por isso o de cima, que pede a tabela alheia, vem junto.
    """
    resposta, corpo = baixar(auth_client, mine.table.id)

    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith("text/csv")
    assert "Empresa" in corpo
    assert str(theirs.record.id) not in corpo
    # Uma linha de cabeçalho e uma de dado — o registro de B não entrou.
    assert len([linha for linha in corpo.splitlines() if linha.strip()]) == 2


def test_the_export_obeys_the_same_filters_as_the_listing(auth_client, mine):
    """
    RS08 na prática: mesmo queryset, mesmos filtros.

    Se a exportação divergisse da listagem, o filtro de dono seria só mais uma
    coisa que poderia divergir junto.
    """
    listagem = auth_client.get(
        reverse("records:record-list", args=[mine.table.id]), {"status": "overdue"}
    )
    _, corpo = baixar(auth_client, mine.table.id, status="overdue")

    assert listagem.data["count"] == 0
    assert len([linha for linha in corpo.splitlines() if linha.strip()]) == 1


def test_a_garbage_token_does_not_get_a_file(api_client, mine):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer nao.e.um.token")

    resposta = api_client.get(reverse("records:record-export", args=[mine.table.id]))

    assert resposta.status_code == 401


def test_the_filename_header_is_readable_by_the_browser(auth_client, mine, settings):
    """
    RF13 — `Content-Disposition` exposto ao JavaScript da SPA.

    O download não pode ser um `<a href>`: a rota exige `Authorization: Bearer`,
    e âncora não carrega header. O cliente busca o arquivo com `fetch` e monta o
    download a partir do blob — e para dar ao arquivo o nome que o servidor
    escolheu, precisa LER o `Content-Disposition`.

    Numa resposta cross-origin o browser esconde todo header que não esteja em
    `Access-Control-Expose-Headers`. Sem esta configuração o CSV baixaria com o
    nome da URL (`export`, sem extensão), e o sintoma só apareceria no browser —
    nunca em `curl`, nunca no teste de API. Daí o tripwire aqui.
    """
    assert "Content-Disposition" in settings.CORS_EXPOSE_HEADERS

    resposta = auth_client.get(
        reverse("records:record-export", args=[mine.table.id]),
        HTTP_ORIGIN="http://localhost:3000",
    )
    b"".join(resposta.streaming_content)

    assert resposta["Content-Disposition"].startswith("attachment; filename=")
    # O header que o browser consulta para decidir o que o script pode ler.
    expostos = resposta.get("access-control-expose-headers", "")
    assert "Content-Disposition" in expostos


def test_the_export_ignores_pagination(auth_client, mine):
    """
    A exportação transmite a queryset filtrada INTEIRA, sem paginar.

    O cliente omite `page` e `page_size` ao exportar. Este teste garante que
    mandá-los por engano não corta o arquivo: quem exporta quer tudo o que o
    filtro seleciona, e um CSV silenciosamente truncado em 50 linhas seria pior
    que um erro.
    """
    from records.models import Record

    Record.objects.bulk_create(
        [
            Record(table=mine.table, user=mine.table.user, data=dict(mine.record.data))
            for _ in range(10)
        ]
    )

    _, sem_paginacao = baixar(auth_client, mine.table.id)
    _, com_paginacao = baixar(auth_client, mine.table.id, page=1, page_size=2)

    assert sem_paginacao == com_paginacao
    # 11 registros + cabeçalho.
    assert len([linha for linha in sem_paginacao.splitlines() if linha.strip()]) == 12
