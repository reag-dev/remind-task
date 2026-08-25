/** Endpoints de `/api/auth/`. */

import { API_URL, request } from "./client.ts";
import type { Usuario } from "./tipos.ts";

export type DadosDeLogin = { email: string; password: string };

export type RespostaDeLogin = {
  access: string;
  /** O refresh **não** vem aqui — sai só no cookie httpOnly. */
  user: Usuario;
};

export type DadosDeCadastro = {
  email: string;
  name: string;
  password: string;
  timezone?: string;
};

export function login(dados: DadosDeLogin): Promise<RespostaDeLogin> {
  return request<RespostaDeLogin>("/auth/login/", { method: "POST", body: dados });
}

export function cadastrar(dados: DadosDeCadastro): Promise<Usuario> {
  return request<Usuario>("/auth/register/", { method: "POST", body: dados });
}

export function eu(): Promise<Usuario> {
  return request<Usuario>("/auth/me/");
}

/**
 * Encerra a sessão.
 *
 * Não passa por `request`: o interceptor de 401 tentaria renovar o token no
 * meio de um logout, o que é exatamente o contrário do pedido. E o endpoint é
 * `AllowAny` de propósito — a autoridade aqui é a posse do cookie, não o access
 * token, que pode já ter expirado.
 *
 * Idempotente no backend (`with suppress(TokenError)`), então falha de rede não
 * precisa bloquear a limpeza do estado local.
 */
export async function logout(): Promise<void> {
  try {
    await fetch(`${API_URL}/auth/logout/`, { method: "POST", credentials: "include" });
  } catch {
    // Sessão local será limpa de qualquer forma; o refresh expira em 7 dias.
  }
}

export type DadosDeRedefinicao = { uid: string; token: string; password: string };

/**
 * Pede o link de recuperação.
 *
 * Sempre 204, exista ou não a conta — a API não conta quais e-mails têm
 * cadastro (ver `tests/security/test_user_enumeration.py`). A tela precisa
 * honrar isso: uma mensagem diferente aqui recriaria, no cliente, o oráculo que
 * o servidor recusa ser.
 */
export function pedirRecuperacao(email: string): Promise<void> {
  return request<void>("/auth/password-reset/", { method: "POST", body: { email } });
}

/**
 * Consome o link e troca a senha.
 *
 * Em caso de sucesso o backend encerra TODAS as sessões em aberto (blacklist dos
 * refresh tokens) — inclusive a de quem estiver logado neste browser.
 */
export function redefinirSenha(dados: DadosDeRedefinicao): Promise<void> {
  return request<void>("/auth/password-reset/confirm/", { method: "POST", body: dados });
}
