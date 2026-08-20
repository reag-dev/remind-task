import { createContext, use } from "react";

import type { Usuario } from "../api/tipos.ts";

/**
 * Três estados, não dois.
 *
 * "Carregando" precisa ser distinto de "anônimo" porque o bootstrap da sessão é
 * assíncrono: a aplicação sobe sem token (ele nunca é persistido) e só descobre
 * se há sessão depois do `POST /auth/refresh/`. Tratar o instante inicial como
 * anônimo faria a `<RotaProtegida>` redirecionar para o login antes da resposta
 * chegar — o usuário logado piscaria para fora a cada F5.
 */
export type EstadoDeAuth =
  | { nome: "carregando" }
  | { nome: "anonimo" }
  | { nome: "autenticado"; usuario: Usuario };

export type Auth = {
  estado: EstadoDeAuth;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: () => Promise<void>;
};

export const ContextoDeAuth = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const auth = use(ContextoDeAuth);
  if (!auth) throw new Error("useAuth precisa estar dentro de <AuthProvider>.");
  return auth;
}
