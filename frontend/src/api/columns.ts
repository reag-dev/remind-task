/** Endpoints de `/api/tables/{id}/columns/` (RF05, RF06). */

import { request, type Pagina } from "./client.ts";
import type { Coluna, TipoDeColuna } from "./tipos.ts";

export type DadosDeColuna = {
  name: string;
  type: TipoDeColuna;
  is_required?: boolean;
  is_sensitive?: boolean;
  options?: string[];
};

export function listarColunas(tabelaId: string): Promise<Pagina<Coluna>> {
  return request<Pagina<Coluna>>(`/tables/${tabelaId}/columns/`);
}

export function criarColuna(tabelaId: string, dados: DadosDeColuna): Promise<Coluna> {
  return request<Coluna>(`/tables/${tabelaId}/columns/`, {
    method: "POST",
    body: dados,
  });
}

/**
 * `type` não entra: o serializer recusa a troca com 400.
 *
 * O motivo está no backend e vale repetir, porque a UI precisa explicá-lo: os
 * registros já gravados foram validados contra o tipo antigo. Trocar o tipo
 * deixaria valores no JSONB que não passam mais na validação — corrupção
 * silenciosa, descoberta só na próxima edição do registro.
 */
export function atualizarColuna(
  tabelaId: string,
  colunaId: string,
  dados: Partial<Omit<DadosDeColuna, "type">>,
): Promise<Coluna> {
  return request<Coluna>(`/tables/${tabelaId}/columns/${colunaId}/`, {
    method: "PATCH",
    body: dados,
  });
}

export function excluirColuna(tabelaId: string, colunaId: string): Promise<void> {
  return request<void>(`/tables/${tabelaId}/columns/${colunaId}/`, {
    method: "DELETE",
  });
}

/**
 * Reordena as colunas.
 *
 * `ordem` precisa conter **todos** os ids da tabela — o `ReorderSerializer`
 * compara o conjunto recebido com o conjunto atual e recusa qualquer diferença.
 * Não é um endpoint de "mover a coluna X para a posição N": é a permutação
 * inteira, aplicada numa transação só. A constraint de posição é DEFERRABLE
 * justamente para os estados intermediários duplicados não quebrarem nada.
 */
export function reordenarColunas(
  tabelaId: string,
  ordem: string[],
): Promise<Coluna[]> {
  return request<Coluna[]>(`/tables/${tabelaId}/columns/reorder/`, {
    method: "PATCH",
    body: { order: ordem },
  });
}
