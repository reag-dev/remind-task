"""
Paginação com tamanho de página controlado pelo cliente — e com teto.

Por que o cliente precisa disso
-------------------------------
O `PageNumberPagination` padrão do DRF ignora `?page_size=` em silêncio quando
`page_size_query_param` não está definido. Um seletor de "linhas por página" na
interface pareceria funcionar — a tabela mudaria de estado, a API continuaria
devolvendo 50, e a contagem de páginas ficaria errada sem nenhum erro. Falha
silenciosa é o que este projeto vem evitando em toda camada.

Por que o teto não é decoração
------------------------------
Sem `max_page_size`, `?page_size=100000` vira varredura de tabela. E não é uma
varredura barata: cada linha de `records` carrega o `data` JSONB inteiro, que é
justamente onde moram os valores das colunas marcadas `is_sensitive`. Uma única
requisição transferiria a base toda do usuário — e o custo cai no servidor, não
em quem pediu.

200 é folgado para uso real (o maior grid do MVP tem uma dúzia de colunas) e
continua ordens de grandeza abaixo do que causaria problema.

A exportação CSV (RF13) não passa por aqui: ela transmite a queryset filtrada
inteira em streaming, por design, sem paginar. Quem precisa de tudo usa o
export, que foi feito para isso.
"""

from rest_framework.pagination import PageNumberPagination


class PaginacaoPadrao(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
