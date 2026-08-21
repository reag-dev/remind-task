/** Endpoints de `/api/tables/` (RF03, RF04). */

import { request, type Pagina } from "./client.ts";
import type { Tabela } from "./tipos.ts";

export type DadosDeTabela = {
  name: string;
  description?: string;
  alert_lead_days?: number;
};

/**
 * A resposta é paginada (`PAGE_SIZE = 50`).
 *
 * A Phase 2 devolve a página inteira e ignora `count` de propósito — a Phase 5
 * troca isto pelo hook de paginação compartilhado. Quem consome não deve
 * assumir que `results` é a coleção completa.
 */
export function listarTabelas(): Promise<Pagina<Tabela>> {
  return request<Pagina<Tabela>>("/tables/");
}

export function obterTabela(id: string): Promise<Tabela> {
  return request<Tabela>(`/tables/${id}/`);
}

export function criarTabela(dados: DadosDeTabela): Promise<Tabela> {
  return request<Tabela>("/tables/", { method: "POST", body: dados });
}

export function atualizarTabela(
  id: string,
  dados: Partial<DadosDeTabela>,
): Promise<Tabela> {
  return request<Tabela>(`/tables/${id}/`, { method: "PATCH", body: dados });
}

export function excluirTabela(id: string): Promise<void> {
  return request<void>(`/tables/${id}/`, { method: "DELETE" });
}
