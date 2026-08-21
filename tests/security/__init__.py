"""
Suíte de segurança do MVP — seção 10 da especificação.

Cada critério da lista tem um teste que **falha se a proteção sumir**. É essa a
função da suíte: não demonstrar que a proteção existe hoje (os testes de cada app
já fazem isso de passagem), e sim garantir que remover uma linha de `get_queryset`
ou trocar uma classe de permissão quebre a build.

| # | Critério da seção 10 | Onde é provado |
|---|---|---|
| 1 | A não acessa tabelas de B | `test_cross_tenant.py` |
| 2 | A não edita registros de B | `test_cross_tenant.py` |
| 3 | A não exclui registros de B | `test_cross_tenant.py` |
| 4 | Endpoints protegidos exigem autenticação | `test_auth_required.py` |
| 5 | Senhas não ficam em texto puro | `test_credentials.py` |
| 6 | HTTPS em produção | `test_transport.py` |
| 7 | Dado sensível não aparece em log | `test_logging_redaction.py` |
| 8 | Export exige autenticação e autorização | `test_export_authorization.py` |
| 9 | Acesso indevido é tratado com segurança (404, nunca 403) | `test_cross_tenant.py` |
| 10 | Alerta não expõe dado sensível | `test_logging_redaction.py` |

Além dos dez, `test_queryset_layer.py` prova a PRIMEIRA barreira sozinha, com a
RLS fora de cena. Sem ele, apagar o filtro por dono de um `get_queryset()` não
quebraria teste nenhum — a RLS filtraria a mesma consulta no banco e a API
continuaria correta. Defesa em profundidade é isso, e é bom; o risco é a camada 1
sumir em silêncio e o sistema ficar sem nada no dia em que a RLS não valer.

Os testes olham a superfície da API, não o interior das funções. Um teste que
chamasse `get_queryset()` direto continuaria verde se alguém trocasse a rota.
"""
