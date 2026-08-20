"""
Middleware de apoio ao RLS (RS01).
"""

from core import rls


class RowLevelSecurityMiddleware:
    """
    Garante que a conexão volte ao papel de login ao fim de cada request.

    Quem *entra* no contexto de RLS são as classes de autenticação
    (`core.rls.RLSJWTAuthentication`), porque é lá que se sabe quem é o usuário
    — a autenticação do DRF acontece dentro da view, não num middleware. Aqui só
    fica a saída, que precisa de um lugar que rode mesmo quando a view levanta
    exceção.

    Deve ser o ÚLTIMO da lista `MIDDLEWARE`: assim é o mais interno, e a limpeza
    acontece antes de o SessionMiddleware gravar a sessão — que é uma escrita em
    tabela e não deve herdar o papel rebaixado.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            rls.leave()
