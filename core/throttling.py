"""
Limitadores de taxa que **falham abertos**.

O throttle do DRF guarda os contadores no cache. Com o cache no Redis — que é o
que faz o limite valer para o conjunto dos workers, e não para cada um — uma
queda do Redis passaria a derrubar a aplicação inteira: `cache.get()` levanta,
a exceção sobe pela view e todo request vira 500.

Isso seria uma troca ruim. Antes desta phase, o Redis fora do ar interrompia os
alertas e nada mais; o caminho de request nem o tocava. Uma medida de proteção
não deveria ampliar a superfície de indisponibilidade que ela existe para
reduzir.

Então o comportamento aqui é o padrão de qualquer limitador sério: **cache
indisponível libera a requisição**, e registra. Perde-se o teto enquanto o Redis
está fora — que é exatamente a situação em que já se está de olho no sistema —,
mas o serviço continua respondendo.
"""

import logging

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


class FailOpenMixin:
    """
    Libera a requisição quando o backend de cache não responde.

    `Exception` e não uma lista de tipos: cada backend de cache levanta a sua
    própria família (`redis.ConnectionError`, `TimeoutError`, erros de
    serialização…), e enumerá-las aqui garantiria descobrir a que faltou em
    produção, num 500. O que interessa é a decisão, e ela é a mesma para
    qualquer falha do cache.
    """

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.warning(
                "Cache indisponível: %s liberou a requisição sem aplicar o "
                "limite de taxa.",
                type(self).__name__,
                exc_info=True,
            )
            return True


class UsuarioThrottle(FailOpenMixin, UserRateThrottle):
    pass


class AnonimoThrottle(FailOpenMixin, AnonRateThrottle):
    pass


class ExportacaoThrottle(FailOpenMixin, UserRateThrottle):
    """
    Teto separado para a exportação, por usuário.

    `UserRateThrottle` com `scope` trocado, e não `ScopedRateThrottle`: o
    caminho do escopo exige que a VIEW declare `throttle_scope`, e num
    `@action` de ViewSet esse atributo vira initkwarg — que o
    `ViewSet.as_view()` rejeita com `TypeError`, derrubando o urlconf inteiro
    no import. Um atributo de classe aqui resolve sem esse acoplamento.

    A taxa continua vindo de `DEFAULT_THROTTLE_RATES["export"]`.
    """

    scope = "export"
