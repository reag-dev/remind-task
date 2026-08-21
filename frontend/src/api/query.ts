import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./client.ts";

/**
 * Chaves de query, num lugar só.
 *
 * Invalidação depende de as chaves baterem exatamente. Espalhar
 * `["tabelas", id]` literal por seis arquivos é o caminho conhecido para a tela
 * que não atualiza depois de um POST — e o sintoma aparece longe da causa.
 */
export const chaves = {
  tabelas: ["tabelas"] as const,
  tabela: (id: string) => ["tabelas", id] as const,
  colunas: (tabelaId: string) => ["tabelas", tabelaId, "colunas"] as const,
  registros: (tabelaId: string) => ["tabelas", tabelaId, "registros"] as const,
  /**
   * Registros com filtros/ordenação/página — a chave carrega a consulta.
   *
   * É o que faz o TanStack Query tratar cada combinação como um recurso
   * próprio, em vez de sobrescrever o cache a cada troca de filtro. Invalidar
   * `registros(id)` alcança todas elas por prefixo.
   */
  registrosCom: (tabelaId: string, consulta: Record<string, unknown>) =>
    ["tabelas", tabelaId, "registros", consulta] as const,
  regras: (tabelaId: string) => ["tabelas", tabelaId, "regras"] as const,

  /**
   * Alertas ficam FORA da árvore `["tabelas", ...]`.
   *
   * A caixa de entrada é do usuário, não de uma tabela — ela mistura alertas de
   * todas elas. Pendurá-la sob `["tabelas", id]` faria uma edição de tabela
   * qualquer invalidar a inbox inteira, e o contador do cabeçalho piscaria a
   * cada renomeação.
   */
  alertas: ["alertas"] as const,
  alertasCom: (consulta: Record<string, unknown>) => ["alertas", consulta] as const,
};

/**
 * As chaves são hierárquicas de propósito.
 *
 * `invalidateQueries` casa por PREFIXO, então invalidar `["tabelas"]` alcança
 * também `["tabelas", id]` e `["tabelas", id, "colunas"]`. É o que se quer
 * depois de excluir uma tabela — o detalhe e as colunas dela morrem junto — e é
 * a razão de o id vir antes do sub-recurso, e não `["colunas", tabelaId]`.
 *
 * O outro lado da moeda: uma mutação de coluna deve invalidar
 * `chaves.tabela(id)` (para o `columns[]` embutido no detalhe voltar correto),
 * não `chaves.tabelas` inteiro — senão toda edição de coluna descarta o cache
 * da lista de tabelas sem motivo.
 */

/**
 * Não repetir requisição que falhou por 4xx.
 *
 * O padrão do TanStack Query são 3 tentativas para qualquer erro. Aqui isso é
 * ativamente ruim:
 *
 * - **401** já tem tratamento próprio — `request` renova o token e repete uma
 *   vez. Somar o retry da query por cima multiplicaria as chamadas ao
 *   `/auth/refresh/`, e com rotação + blacklist cada refresh extra é um token
 *   queimado. É a armadilha 2 voltando por outra porta.
 * - **404** é a resposta desenhada para recurso de outro dono (RS04). Insistir
 *   três vezes num recurso que por definição não vai aparecer só gera ruído no
 *   log do servidor.
 * - **400** é erro de validação. Repetir o mesmo corpo dá o mesmo 400.
 *
 * 5xx e falha de rede continuam merecendo retry: essas passam.
 */
export function criarQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (tentativas, erro) => {
          if (erro instanceof ApiError && erro.status >= 400 && erro.status < 500) {
            return false;
          }
          return tentativas < 2;
        },
        staleTime: 30_000,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
