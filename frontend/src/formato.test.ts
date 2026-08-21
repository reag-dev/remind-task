import { describe, expect, it } from "vitest";

import { formatarData, formatarNumero, paraTexto, textoDeDias } from "./formato.ts";

describe("formatarData", () => {
  it("nao desloca a data por causa de fuso", () => {
    // O teste que justifica a funcao existir. `new Date("2026-08-20")` e
    // meia-noite UTC; formatado em America/Sao_Paulo (UTC-3) daria 19/08.
    // O vencimento apareceria um dia antes do que e — no produto cujo motivo
    // de existir e nao errar uma data.
    expect(formatarData("2026-08-20")).toBe("20/08/2026");
    expect(formatarData("2026-01-01")).toBe("01/01/2026");
    expect(formatarData("2026-12-31")).toBe("31/12/2026");
  });

  it("aceita data com hora anexada e ignora o resto", () => {
    expect(formatarData("2026-08-20T00:00:00Z")).toBe("20/08/2026");
  });

  it("devolve o valor cru quando nao reconhece o formato", () => {
    // Melhor mostrar o que esta gravado do que uma celula vazia.
    expect(formatarData("nao e data")).toBe("nao e data");
  });
});

describe("paraTexto", () => {
  it.each([
    ["texto", "texto"],
    [42, "42"],
    [0, "0"],
    [true, "true"],
    [false, "false"],
  ])("converte %o em %o", (entrada, esperado) => {
    expect(paraTexto(entrada)).toBe(esperado);
  });

  it("serializa objeto em vez de produzir [object Object]", () => {
    // O `data` e JSONB: a forma so existe em runtime. Um valor estruturado
    // numa coluna de texto e sinal de problema, e o JSON mostra qual.
    expect(paraTexto({ a: 1 })).toBe('{"a":1}');
    expect(paraTexto([1, 2])).toBe("[1,2]");
    expect(paraTexto({ a: 1 })).not.toContain("object Object");
  });
});

describe("formatarNumero", () => {
  it("usa a convencao pt-BR", () => {
    // Separador de milhar ponto, decimal virgula. Um numero formatado em
    // en-US ("1,234.5") seria lido como mil vezes maior por quem le pt-BR.
    expect(formatarNumero(1234.5)).toBe("1.234,5");
    expect(formatarNumero(1000000)).toBe("1.000.000");
  });

  it("nao inventa numero a partir de texto", () => {
    expect(formatarNumero("abc")).toBe("abc");
  });
});

describe("textoDeDias", () => {
  it.each([
    [0, "hoje"],
    [1, "amanhã"],
    [-1, "ontem"],
    [-5, "há 5 dias"],
    [30, "em 30 dias"],
  ])("descreve %i como %s", (dias, esperado) => {
    expect(textoDeDias(dias)).toBe(esperado);
  });
});
