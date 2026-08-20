import { ApiError } from "../api/client.ts";

/**
 * Mensagem de erro de login, em pt-BR.
 *
 * Os dois casos que precisam de tratamento próprio:
 *
 * - **429** — bloqueio do django-axes (`AXES_FAILURE_LIMIT = 5`,
 *   `AXES_COOLOFF_TIME = 15 min`). Verificado contra a API em 2026-08-20: o
 *   bloqueio cai já **na quinta** tentativa, e o corpo vem em **texto puro e em
 *   inglês** ("Account locked: too many login attempts."), não em JSON — é o
 *   `AxesMiddleware` respondendo antes do DRF. Repassar esse texto quebraria o
 *   idioma da interface e não diria ao usuário quanto tempo esperar.
 * - **401** — credencial inválida. A mensagem do SimpleJWT ("No active account
 *   found with the given credentials") também é em inglês, e além disso é vaga.
 *
 * Nenhuma das duas distingue "e-mail não existe" de "senha errada", e isso é
 * proposital: distinguir entregaria a enumeração de contas.
 */
export function mensagemDeLogin(erro: unknown): string {
  if (!(erro instanceof ApiError)) {
    return "Não foi possível falar com o servidor. Verifique sua conexão.";
  }

  if (erro.status === 429) {
    return "Muitas tentativas de login. Tente novamente em 15 minutos.";
  }

  if (erro.status === 401) {
    return "E-mail ou senha inválidos.";
  }

  return erro.message;
}
