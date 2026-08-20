"""
Row-Level Security: a segunda barreira de isolamento (RS01).

A primeira barreira é o `get_queryset()` de cada view, filtrado por
`request.user`. Ela funciona — até alguém escrever `Record.objects.all()` num
relatório, num comando de management ou numa task nova. RLS coloca a mesma regra
dentro do Postgres, onde nenhum código de aplicação consegue esquecê-la.

Como funciona aqui
------------------
O Django conecta com o papel **dono** das tabelas (o `POSTGRES_USER`), que
precisa dessa força para rodar `migrate` e criar o banco de teste. Se as
consultas do runtime usassem esse mesmo papel, as policies não valeriam nada:
superusuário ignora RLS sempre, e o dono ignora se a tabela não tiver
`FORCE ROW LEVEL SECURITY`.

Por isso o runtime **rebaixa o papel dentro da transação**:

    SET LOCAL ROLE remind_app;                  -- NOSUPERUSER, NOBYPASSRLS
    SELECT set_config('app.user_id', <uuid>, true);

`remind_app` não tem LOGIN — não é uma credencial nova para guardar, é só um
papel no qual a conexão entra e do qual sai. Os dois comandos são `LOCAL`: o
Postgres os desfaz sozinho no fim da transação, então uma conexão persistente
(`CONN_MAX_AGE`) nunca leva o usuário de uma request para a seguinte.

Onde isto é acionado
--------------------
1. Requests da API — nas classes de autenticação (`RLSJWTAuthentication`,
   `RLSSessionAuthentication`), que é o primeiro ponto do ciclo em que se sabe
   *quem* é o usuário. Com `ATOMIC_REQUESTS = True` a autenticação já roda
   dentro da transação da request, que é o que `SET LOCAL` exige.
2. Exportação CSV — `exports.services.stream_rows` abre a própria transação,
   porque o corpo de uma `StreamingHttpResponse` é consumido depois que a da
   request fechou.
3. Job de alertas — `alerts.tasks.scan_due_records`, uma transação por usuário.

O Django Admin fica **de fora**: ele autentica por sessão, sem passar pelo DRF, e
continua consultando como dono. É uma ferramenta de staff, e um admin que só
enxerga as próprias linhas não serve para suporte. Documentado no README.
"""

import logging
from contextlib import contextmanager

from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger(__name__)

# Papel sem LOGIN em que a conexão entra durante o request. Criado na migration
# core.0001. O nome é constante de código porque vai concatenado no SQL:
# SET ROLE não aceita placeholder.
RUNTIME_ROLE = "remind_app"

GUC = "app.user_id"


def enter(user_id) -> None:
    """
    Rebaixa a transação corrente para `remind_app` em nome de `user_id`.

    Falha alto se não houver transação aberta: fora de uma, `SET LOCAL` vira um
    WARNING do Postgres e não aplica nada — as consultas continuariam rodando
    como dono, sem RLS, e sem nada no log da aplicação para denunciar. Um erro
    barulhento é preferível a um isolamento que silenciosamente não existe.
    """
    if not connection.in_atomic_block:
        raise ImproperlyConfigured(
            "core.rls.enter() exige uma transação aberta — SET LOCAL não tem "
            "efeito fora de uma. Verifique ATOMIC_REQUESTS ou envolva a chamada "
            "em transaction.atomic()."
        )

    with connection.cursor() as cursor:
        cursor.execute(f"SET LOCAL ROLE {RUNTIME_ROLE}")
        # set_config(..., is_local=true) é o equivalente de SET LOCAL que aceita
        # parâmetro — SET LOCAL app.user_id = %s não aceita.
        cursor.execute("SELECT set_config(%s, %s, true)", [GUC, str(user_id)])


def leave() -> None:
    """
    Devolve a conexão ao papel de login.

    Em produção seria dispensável: `SET LOCAL` se desfaz no COMMIT. É nos testes
    que importa — pytest-django envolve cada teste numa transação, então a
    transação da request vira um savepoint e o `SET LOCAL` sobrevive ao fim da
    request. Sem esta limpeza, toda asserção feita com o ORM depois de um
    `client.get()` continuaria filtrada por RLS.
    """
    if connection.connection is None:
        return
    if connection.in_atomic_block and connection.needs_rollback:
        # Transação já marcada para rollback: qualquer comando aqui estouraria,
        # e o rollback restaura papel e GUC de qualquer forma.
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config(%s, '', false)", [GUC])
    except Exception:  # pragma: no cover - conexão já morta
        logger.warning("Não foi possível restaurar o papel do banco.", exc_info=True)


@contextmanager
def session(user_id):
    """
    Bloco em que as consultas rodam como `remind_app` em nome de `user_id`.

    Abre a própria transação — é o que `SET LOCAL` exige — e devolve a conexão
    ao papel de login na saída, inclusive quando o corpo levanta exceção ou o
    gerador que a usa é abandonado no meio.
    """
    with transaction.atomic():
        enter(user_id)
        try:
            yield
        finally:
            leave()


class _EnterOnAuthenticate:
    """Entra no contexto de RLS assim que a autenticação identifica o usuário."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            enter(result[0].pk)
        return result


class RLSJWTAuthentication(_EnterOnAuthenticate, JWTAuthentication):
    pass


class RLSSessionAuthentication(_EnterOnAuthenticate, SessionAuthentication):
    pass
