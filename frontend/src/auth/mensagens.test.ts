import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client.ts";
import { mensagemDeLogin } from "./mensagens.ts";

describe("mensagemDeLogin", () => {
  it("traduz o 429 do axes com o tempo de espera", () => {
    // Verificado contra a API em 2026-08-20: o AxesMiddleware responde antes do
    // DRF, com corpo em texto puro e em ingles.
    const erro = new ApiError(429, { detail: "Account locked: too many attempts." });

    const mensagem = mensagemDeLogin(erro);

    expect(mensagem).toContain("Muitas tentativas");
    expect(mensagem).toContain("15 minutos");
    expect(mensagem).not.toContain("Account locked");
  });

  it("nao distingue e-mail inexistente de senha errada no 401", () => {
    // Distinguir entregaria a enumeracao de contas.
    const erro = new ApiError(401, { detail: "No active account found" });

    expect(mensagemDeLogin(erro)).toBe("E-mail ou senha inválidos.");
  });

  it("fala de conexao quando nem chegou a ser um erro da API", () => {
    // TypeError de fetch, CORS recusado, servidor fora. Nenhum desses tem
    // `status`, e repassar "Failed to fetch" nao ajuda ninguem.
    expect(mensagemDeLogin(new TypeError("Failed to fetch"))).toMatch(
      /não foi possível falar com o servidor/i,
    );
  });

  it("repassa a mensagem da API em status inesperado", () => {
    const erro = new ApiError(503, { detail: "Em manutenção." });

    expect(mensagemDeLogin(erro)).toBe("Em manutenção.");
  });
});
