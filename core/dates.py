"""
"Hoje" no fuso do usuário.

O servidor roda em UTC (`TIME_ZONE = "UTC"`). Usar `date.today()` daria a data do
servidor: para quem está em São Paulo (UTC-3), das 21h à meia-noite o sistema já
teria virado o dia e mostraria um contrato como "vencido" um dia antes da hora.
Do outro lado, alguém em Tóquio veria o vencimento um dia atrasado.

Como o status de vencimento (RF10) e o disparo de alertas (RF12) são decididos
comparando datas, a referência precisa ser a do usuário — não a do servidor.
"""

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

FALLBACK_TIMEZONE = "UTC"


def user_today(user) -> date:
    """Data corrente no fuso declarado pelo usuário."""
    return today_in(getattr(user, "timezone", None))


def today_in(tz_name: str | None) -> date:
    try:
        zone = ZoneInfo(tz_name) if tz_name else ZoneInfo(FALLBACK_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        # O model valida contra a lista IANA; isto cobre um valor que tenha
        # entrado por escrita direta no banco. Melhor cair para UTC do que
        # derrubar a listagem inteira.
        zone = ZoneInfo(FALLBACK_TIMEZONE)
    return timezone.localdate(timezone=zone)
