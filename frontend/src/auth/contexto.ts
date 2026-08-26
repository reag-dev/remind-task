import { createContext, use } from "react";

import type { Usuario } from "../api/tipos.ts";

/**
 * Por que "anônimo" carrega um motivo.
 *
 * Nem toda saída é igual, e a diferença muda o destino: sessão expirada volta
 * para onde estava (`?next=`), conta excluída não tem para onde voltar. Quem
 * decide o destino de um anônimo é a `<RotaProtegida>`, então é ela que precisa
 * saber o motivo — a alternativa, cada tela navegar por conta própria depois de
 * chamar `sair()`, perde uma corrida que não dá para ganhar: o React Router
 * navega dentro de uma transition e o `setState` do logout é urgente, então o
 * guard renderiza primeiro e o `<Navigate>` dele atropela o da tela.
 */
export type MotivoDeSaida = "conta-excluida";

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
  | { nome: "anonimo"; motivo?: MotivoDeSaida }
  | { nome: "autenticado"; usuario: Usuario };

export type Auth = {
  estado: EstadoDeAuth;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: (motivo?: MotivoDeSaida) => Promise<void>;
};

export const ContextoDeAuth = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const auth = use(ContextoDeAuth);
  if (!auth) throw new Error("useAuth precisa estar dentro de <AuthProvider>.");
  return auth;
}
