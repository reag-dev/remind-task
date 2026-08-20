/**
 * Renovação do access token, com single-flight.
 *
 * Por que single-flight não é otimização
 * -------------------------------------
 * O backend roda SimpleJWT com `ROTATE_REFRESH_TOKENS` e
 * `BLACKLIST_AFTER_ROTATION` (ver `config/settings/base.py`). Cada
 * `POST /auth/refresh/` bem-sucedido emite um refresh novo e **queima o
 * anterior**.
 *
 * Uma tela do app dispara várias requisições em paralelo — a lista de tabelas,
 * a contagem de alertas, o /auth/me/. Quando o access token expira, elas tomam
 * 401 praticamente juntas. Se cada uma renovasse por conta própria:
 *
 *   req A → refresh(T0) → ok, emite T1, queima T0
 *   req B → refresh(T0) → T0 está na blacklist → 401
 *   req C → refresh(T0) → idem → 401
 *
 * O usuário seria deslogado por ter aberto uma tela com três chamadas. Pior: de
 * forma intermitente, porque depende de as respostas chegarem próximas o
 * suficiente. Com single-flight, a primeira chamada renova e as demais esperam
 * a mesma promessa.
 *
 * O cookie de refresh é httpOnly e tem `path=/api/auth/`: este módulo nunca vê
 * o token, só provoca o browser a enviá-lo com `credentials: "include"`.
 */

import { API_URL } from "../api/client.ts";

/** Promessa em voo, ou `null` quando não há renovação acontecendo. */
let emVoo: Promise<string | null> | null = null;

/**
 * Renova o access token, no máximo uma vez por vez.
 *
 * Devolve o token novo, ou `null` quando a sessão acabou (refresh ausente,
 * expirado ou já na blacklist). Nunca lança: quem chama trata `null` como
 * "deslogue", e um throw aqui viraria erro não tratado dentro do interceptor.
 */
export function renovarAccessToken(): Promise<string | null> {
  // O ponto todo: quem chegar enquanto uma renovação está em voo recebe a
  // MESMA promessa, em vez de disparar a sua.
  emVoo ??= executar().finally(() => {
    emVoo = null;
  });

  return emVoo;
}

async function executar(): Promise<string | null> {
  try {
    const resposta = await fetch(`${API_URL}/auth/refresh/`, {
      method: "POST",
      // Sem isto o cookie httpOnly não é enviado e o backend responde 401 com
      // "Refresh token ausente." — o modo de falha mais comum deste desenho.
      credentials: "include",
    });

    if (!resposta.ok) return null;

    const corpo = (await resposta.json()) as { access?: string };
    return corpo.access ?? null;
  } catch {
    // Rede fora, CORS recusado, servidor caído. Nada disso distingue de sessão
    // encerrada do ponto de vista de quem chamou.
    return null;
  }
}

/** Só para os testes: descarta a promessa em voo entre casos. */
export function _limparEstadoDeRefresh(): void {
  emVoo = null;
}
