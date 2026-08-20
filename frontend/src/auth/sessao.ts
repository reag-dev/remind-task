/**
 * O access token vivo, fora do React.
 *
 * Por que fora: o cliente HTTP precisa ler o token **de forma síncrona**, no
 * momento de montar o header, e ele é chamado de dentro de efeitos, de handlers
 * e do interceptor de 401 — nenhum desses lugares tem acesso a hook. Guardar
 * só em `useState` obrigaria a passar o token como argumento por toda a árvore
 * de chamadas da API.
 *
 * O `AuthProvider` espelha este valor em estado do React para renderizar; a
 * fonte da verdade para requisições é aqui.
 *
 * Continua sendo memória do processo, que é o requisito real: `localStorage` e
 * `sessionStorage` são legíveis por qualquer JavaScript da página, e um XSS
 * levaria o token junto. Recarregar a aba perde este valor de propósito — é o
 * que o bootstrap de refresh reconstrói.
 */

import { registrarFonteDeToken } from "../api/client.ts";

let accessToken: string | null = null;

export function lerAccessToken(): string | null {
  return accessToken;
}

export function gravarAccessToken(token: string | null): void {
  accessToken = token;
}

// No escopo do módulo, não num efeito do provider: efeitos de componentes
// filhos rodam ANTES dos do pai, então uma tela que dispara fetch no seu
// próprio efeito sairia sem Authorization se a fonte fosse registrada no
// efeito do AuthProvider.
registrarFonteDeToken(lerAccessToken);
