"""
Validação do payload JSONB contra a definição de colunas da tabela.

Sem EAV, o banco não sabe o tipo de cada valor — quem garante é esta camada.
Por isso ela é estrita: chave desconhecida, tipo errado ou opção fora da lista
resultam em 400, nunca em gravação silenciosa de lixo no `data`.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from tables.models import ColumnType

# Teto defensivo: o JSONB aceitaria megabytes numa única célula, e um campo de
# texto livre é a porta mais fácil para inflar o banco e o CSV de exportação.
TEXT_MAX_LENGTH = 5_000


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _coerce_text(value, column):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Esperado texto.")
    text = str(value).strip()
    if len(text) > TEXT_MAX_LENGTH:
        raise ValueError(f"Texto acima de {TEXT_MAX_LENGTH} caracteres.")
    return text


def _coerce_number(value, column):
    if isinstance(value, bool):
        raise ValueError("Esperado número.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("Esperado número.") from None

    # JSON não tem Decimal. Inteiro vira int; o resto vira float, com a precisão
    # de double que o jsonb usa na leitura. Suficiente para o domínio (prazos,
    # contagens, valores de contrato); não usar para cálculo financeiro exato.
    return int(number) if number == number.to_integral_value() else float(number)


def _coerce_date(value, column):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError("Esperado data no formato AAAA-MM-DD.") from None


def _coerce_datetime(value, column):
    if isinstance(value, datetime):
        return value.isoformat()
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ValueError("Esperado data e hora no formato ISO 8601.")
    return parsed.isoformat()


def _coerce_boolean(value, column):
    # Estrito de propósito: JSON tem booleano nativo, então "true" como string é
    # bug do cliente. Aceitar silenciosamente esconderia o erro.
    if not isinstance(value, bool):
        raise ValueError("Esperado true ou false (booleano, não texto).")
    return value


def _coerce_email(value, column):
    text = str(value).strip()
    try:
        EmailValidator()(text)
    except DjangoValidationError:
        raise ValueError("E-mail inválido.") from None
    return text


def _coerce_select(value, column):
    text = str(value).strip()
    if text not in column.options:
        raise ValueError(f"Valor fora das opções: {', '.join(column.options)}.")
    return text


COERCERS = {
    ColumnType.TEXT: _coerce_text,
    ColumnType.NUMBER: _coerce_number,
    ColumnType.DATE: _coerce_date,
    ColumnType.DATETIME: _coerce_datetime,
    ColumnType.BOOLEAN: _coerce_boolean,
    ColumnType.EMAIL: _coerce_email,
    ColumnType.SELECT: _coerce_select,
    ColumnType.DUE_DATE: _coerce_date,
}


def validate_record_data(payload, columns) -> dict:
    """
    Confere o payload inteiro contra as colunas e devolve o `data` normalizado.

    Recebe o estado COMPLETO do registro, não o delta — o PATCH mescla antes de
    chamar. É o que permite checar `is_required` de forma correta: um PATCH que
    apaga um campo obrigatório precisa falhar, e olhando só o delta isso passaria.
    """
    if not isinstance(payload, dict):
        raise serializers.ValidationError({"data": "Deve ser um objeto."})

    by_key = {column.key: column for column in columns}

    unknown = set(payload) - set(by_key)
    if unknown:
        raise serializers.ValidationError(
            {"data": f"Coluna(s) inexistente(s) nesta tabela: {', '.join(sorted(unknown))}."}
        )

    errors: dict[str, str] = {}
    cleaned: dict = {}

    for key, column in by_key.items():
        value = payload.get(key)

        if _empty(value):
            if column.is_required:
                errors[key] = "Campo obrigatório."
            else:
                cleaned[key] = None
            continue

        try:
            cleaned[key] = COERCERS[column.type](value, column)
        except ValueError as exc:
            errors[key] = str(exc)

    if errors:
        raise serializers.ValidationError({"data": errors})

    return cleaned
