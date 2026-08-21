/**
 * Política de retry.
 *
 * Não é ajuste fino de performance: com `ROTATE_REFRESH_TOKENS` +
 * `BLACKLIST_AFTER_ROTATION`, repetir uma requisição que tomou 401 faz o
 * interceptor renovar de novo, e cada renovação queima um refresh token. O
 * retry padrão do TanStack Query (3 tentativas para qualquer erro) traria a
 * armadilha 2 de volta por uma porta diferente da que o single-flight fecha.
 */

import { QueryObserver } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { request } from "./client.ts";
import { criarQueryClient } from "./query.ts";

/** Roda uma query até ela assentar e devolve quantas vezes a rota foi chamada. */
async function contarTentativas(status: number): Promise<number> {
  const chamadas = vi.fn();
  servidor.use(
    http.get(`${API}/tables/`, () => {
      chamadas();
      return HttpResponse.json({ detail: "não" }, { status });
    }),
  );

  const cliente = criarQueryClient();
  const observador = new QueryObserver(cliente, {
    queryKey: ["teste", status],
    queryFn: () => request("/tables/"),
    // Sem espera entre tentativas: a política aqui é "quantas", não "quando".
    retryDelay: 0,
  });

  await new Promise<void>((resolver) => {
    const cancelar = observador.subscribe((resultado) => {
      if (resultado.isError || resultado.isSuccess) {
        cancelar();
        resolver();
      }
    });
  });

  cliente.clear();
  return chamadas.mock.calls.length;
}

describe("criarQueryClient", () => {
  it.each([
    [400, "erro de validação — repetir dá o mesmo 400"],
    [401, "já tratado pelo interceptor; repetir queimaria refresh tokens"],
    [403, "autorização não muda por insistência"],
    [404, "resposta desenhada para recurso de outro dono (RS04)"],
  ])("não repete um %i (%s)", async (status) => {
    expect(await contarTentativas(status)).toBe(1);
  });

  it("repete um 500, que pode ser transitório", async () => {
    // 1 original + 2 retries.
    expect(await contarTentativas(500)).toBe(3);
  });

  it("não repete mutações", () => {
    const cliente = criarQueryClient();
    expect(cliente.getDefaultOptions().mutations?.retry).toBe(false);
    // Repetir uma mutação significa repetir um POST/DELETE. Sem chave de
    // idempotência no backend, isso cria a tabela duas vezes.
  });
});
