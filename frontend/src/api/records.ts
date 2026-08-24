/** Endpoints de `/api/tables/{id}/records/` (RF07-RF11). */

import { request, type Pagina } from "./client.ts";
import type { DadosDoRegistro, Registro } from "./tipos.ts";

/**
 * Parâmetros de consulta.
 *
 * Declarados aqui, exercitados na Phase 5. O backend já os aceita — ver
 * `RecordFilter` e `NullsLastOrderingFilter`.
 */
export type ConsultaDeRegistros = {
  page?: number;
  /**
   * Busca por substring, sem diferenciar maiúsculas.
   *
   * O backend varre apenas as colunas de texto e e-mail da tabela, e **pula as
   * marcadas como sensíveis** — ver `RecordFilter.filter_search`. A UI não
   * precisa saber quais são: quem decide é quem tem o modelo.
   */
  q?: string;
  /** Um ou mais status separados por vírgula. */
  status?: string;
  due_before?: string;
  due_after?: string;
  has_due_date?: boolean;
  ordering?: string;
};

export function listarRegistros(
  tabelaId: string,
  consulta: ConsultaDeRegistros = {},
): Promise<Pagina<Registro>> {
  return request<Pagina<Registro>>(`/tables/${tabelaId}/records/`, { query: consulta });
}

export function criarRegistro(
  tabelaId: string,
  data: DadosDoRegistro,
): Promise<Registro> {
  return request<Registro>(`/tables/${tabelaId}/records/`, {
    method: "POST",
    body: { data },
  });
}

/**
 * PATCH manda o registro INTEIRO, não o delta.
 *
 * O `validate_data` do serializer mescla o delta sobre o valor atual antes de
 * validar, justamente para conseguir checar `is_required` olhando o estado
 * final. Mandar o objeto completo mantém o que a tela mostra e o que o banco
 * guarda em correspondência direta — e evita depender dessa mesclagem para
 * apagar um campo.
 */
export function atualizarRegistro(
  tabelaId: string,
  registroId: string,
  data: DadosDoRegistro,
): Promise<Registro> {
  return request<Registro>(`/tables/${tabelaId}/records/${registroId}/`, {
    method: "PATCH",
    body: { data },
  });
}

export function excluirRegistro(tabelaId: string, registroId: string): Promise<void> {
  return request<void>(`/tables/${tabelaId}/records/${registroId}/`, {
    method: "DELETE",
  });
}
