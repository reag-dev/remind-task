/**
 * Armadilha 2 do plano: rotação de refresh com blacklist.
 *
 * O backend queima o refresh anterior a cada renovação
 * (`ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`). Duas renovações
 * concorrentes significam que a segunda usa um token já invalidado e derruba a
 * sessão. Estes testes existem para que essa regressão apareça aqui, e não como
 * um logout intermitente em produção.
 */

import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { registrarRenovacao, request } from "../api/client.ts";
import { API, servidor } from "../test/servidor.ts";
import { renovarAccessToken } from "./refresh.ts";
import { gravarAccessToken } from "./sessao.ts";

describe("renovarAccessToken", () => {
  it("dispara uma única requisição para três chamadas concorrentes", async () => {
    const chamadas = vi.fn();
    servidor.use(
      http.post(`${API}/auth/refresh/`, async () => {
        chamadas();
        // Latência artificial: sem ela as três chamadas poderiam serializar por
        // acidente de escalonamento e o teste passaria sem provar nada.
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json({ access: "token-novo" });
      }),
    );

    const resultados = await Promise.all([
      renovarAccessToken(),
      renovarAccessToken(),
      renovarAccessToken(),
    ]);

    expect(chamadas).toHaveBeenCalledTimes(1);
    expect(resultados).toEqual(["token-novo", "token-novo", "token-novo"]);
  });

  it("permite uma nova renovação depois que a anterior termina", async () => {
    const chamadas = vi.fn();
    servidor.use(
      http.post(`${API}/auth/refresh/`, () => {
        chamadas();
        return HttpResponse.json({ access: "token-novo" });
      }),
    );

    await renovarAccessToken();
    await renovarAccessToken();

    // O single-flight agrupa concorrentes; não é cache. Renovar de novo mais
    // tarde tem de funcionar, senão o app pararia após o primeiro refresh.
    expect(chamadas).toHaveBeenCalledTimes(2);
  });

  it("devolve null quando o refresh não vale mais, sem lançar", async () => {
    servidor.use(
      http.post(`${API}/auth/refresh/`, () =>
        HttpResponse.json({ detail: "Refresh token ausente." }, { status: 401 }),
      ),
    );

    await expect(renovarAccessToken()).resolves.toBeNull();
  });

  it("envia credenciais, senão o cookie httpOnly não acompanha", async () => {
    let comCredenciais: RequestCredentials | undefined;
    servidor.use(
      http.post(`${API}/auth/refresh/`, ({ request: requisicao }) => {
        comCredenciais = requisicao.credentials;
        return HttpResponse.json({ access: "token-novo" });
      }),
    );

    await renovarAccessToken();

    expect(comCredenciais).toBe("include");
  });
});

describe("interceptor de 401 do cliente", () => {
  it("renova uma vez só para três requisições que expiram juntas", async () => {
    const refreshes = vi.fn();
    let tokenValido = "token-novo";
    gravarAccessToken("token-velho");

    servidor.use(
      http.post(`${API}/auth/refresh/`, async () => {
        refreshes();
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json({ access: tokenValido });
      }),
      http.get(`${API}/tables/`, ({ request: requisicao }) => {
        const header = requisicao.headers.get("Authorization");
        if (header !== `Bearer ${tokenValido}`) {
          return HttpResponse.json({ detail: "expirado" }, { status: 401 });
        }
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );

    // Liga o interceptor do mesmo jeito que o AuthProvider faz.
    registrarRenovacao(async () => {
      const token = await renovarAccessToken();
      if (!token) return false;
      gravarAccessToken(token);
      return true;
    });

    const respostas = await Promise.all([
      request<{ count: number }>("/tables/"),
      request<{ count: number }>("/tables/"),
      request<{ count: number }>("/tables/"),
    ]);

    expect(refreshes).toHaveBeenCalledTimes(1);
    expect(respostas.map((r) => r.count)).toEqual([0, 0, 0]);
    tokenValido = "";
  });

  it("não entra em laço quando o 401 persiste depois da renovação", async () => {
    const requisicoes = vi.fn();
    gravarAccessToken("token-velho");

    servidor.use(
      http.post(`${API}/auth/refresh/`, () =>
        HttpResponse.json({ access: "outro-token" }),
      ),
      http.get(`${API}/tables/`, () => {
        requisicoes();
        return HttpResponse.json({ detail: "sem permissão" }, { status: 401 });
      }),
    );

    registrarRenovacao(async () => {
      const token = await renovarAccessToken();
      if (!token) return false;
      gravarAccessToken(token);
      return true;
    });

    await expect(request("/tables/")).rejects.toMatchObject({ status: 401 });
    // Original + uma repetição. Uma terceira significaria laço.
    expect(requisicoes).toHaveBeenCalledTimes(2);
  });
});
