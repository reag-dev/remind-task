from zoneinfo import available_timezones

from django.core.exceptions import ValidationError


def validate_timezone(value: str) -> None:
    """
    Aceita apenas identificadores IANA reais.

    O fuso do usuário decide o que é "hoje" no cálculo de status de vencimento
    (RF10) e na geração de alertas (RF12). Um valor inválido aqui vira exceção
    dentro do job Celery, longe da origem do erro — então valida na entrada.
    """
    if value not in available_timezones():
        raise ValidationError(
            "%(value)s não é um fuso horário IANA válido (ex.: America/Sao_Paulo).",
            params={"value": value},
        )
