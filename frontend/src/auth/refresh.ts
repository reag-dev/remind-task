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
 *
 * Por que single-flight sozinho não bastava: as abas
 * --------------------------------------------------
 * `emVoo` é uma variável de MÓDULO, e módulo vive no contexto JS da aba. Duas
 * abas são duas cópias dele — o single-flight não coordena nada entre elas. O
 * cookie, esse é do browser: as duas mandam o mesmo token, e a rotação do
 * backend reproduz a corrida acima entre abas em vez de dentro de uma.
 *
 * O sintoma não era "deslogou": era `encerrarLocalmente()` na aba perdedora
 * enquanto o cookie novo continuava válido, ou seja **"me deslogou do nada,
 * atualizei e voltou"** — intermitente, e só quando duas abas cruzam o
 * vencimento do access na mesma janela de um round-trip.
 *
 * A serialização é feita com `navigator.locks` (Web Locks), que é a primitiva
 * da plataforma para exclusão mútua entre abas da mesma origem. Serializar
 * basta, e **deduplicar seria errado**: cada aba guarda o access token na
 * própria memória, então cada uma precisa mesmo do seu. O que não pode é
 * renovarem juntas.
 *
 * O que fecha a corrida é a ordem em que o browser processa a resposta: o
 * `Set-Cookie` é aplicado ao receber os CABEÇALHOS, antes de o corpo chegar ao
 * JS. Quando a aba A solta o lock — o que só acontece depois do
 * `await resposta.json()` —, o cookie já é o token novo, e a aba B renova em
 * cima dele.
 */

import { API_URL } from "../api/client.ts";

/** Promessa em voo, ou `null` quando não há renovação acontecendo. */
let emVoo: Promise<string | null> | null = null;

/** Escopo do lock é a origem, que pode ser compartilhada — daí o prefixo. */
const LOCK = "remind-task:renovar-access-token";

/**
 * Teto de espera pelo lock.
 *
 * Um lock preso é pior que a corrida que ele evita: travaria a renovação da
 * aba, e com ela a sessão, sem erro nenhum na tela. Passado o teto, esta aba
 * renova sem serializar — volta ao risco antigo, que é intermitente, em vez de
 * um travamento certo.
 */
const ESPERA_MAXIMA_MS = 5000;

/**
 * Renova o access token, no máximo uma vez por vez.
 *
 * Devolve o token novo, ou `null` quando a sessão acabou (refresh ausente,
 * expirado ou já na blacklist). Nunca lança: quem chama trata `null` como
 * "deslogue", e um throw aqui viraria erro não tratado dentro do interceptor.
 */
export function renovarAccessToken(): Promise<string | null> {
  // Duas travas, uma para cada escopo: `emVoo` agrupa as chamadas DESTA aba, e
  // o lock impede que ABAS diferentes renovem ao mesmo tempo. A ordem importa —
  // dedupe primeiro, senão cada chamada da mesma aba pediria o lock à toa.
  emVoo ??= serializarEntreAbas(executar).finally(() => {
    emVoo = null;
  });

  return emVoo;
}

/**
 * Roda `tarefa` com exclusão mútua entre as abas da origem.
 *
 * Degrada para execução direta em dois casos, e nos dois isso é preferível a
 * falhar: quando não há `navigator.locks` (jsdom dos testes, browser antigo) e
 * quando a espera estoura o teto. Sem lock volta-se ao comportamento anterior,
 * que erra às vezes; travar erraria sempre.
 */
async function serializarEntreAbas<T>(tarefa: () => Promise<T>): Promise<T> {
  const locks: LockManager | undefined = navigator.locks;
  if (!locks) return tarefa();

  const controlador = new AbortController();
  const relogio = setTimeout(() => controlador.abort(), ESPERA_MAXIMA_MS);

  try {
    return await locks.request(LOCK, { signal: controlador.signal }, tarefa);
  } catch {
    // Só o PEDIDO do lock falha por aqui (abortado, ou indisponível): `tarefa`
    // é o `executar` abaixo, que trata os próprios erros e nunca lança.
    return tarefa();
  } finally {
    clearTimeout(relogio);
  }
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
