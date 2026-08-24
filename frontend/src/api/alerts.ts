/** Endpoints de `/api/alerts/` e `/api/tables/{id}/alert-rules/` (RF12). */

import { request, type Pagina } from "./client.ts";
import type { Alerta, RegraDeAlerta, StatusDeAlerta } from "./tipos.ts";

export type ConsultaDeAlertas = {
  page?: number;
  page_size?: number;
  status?: StatusDeAlerta;
};

export function listarAlertas(consulta: ConsultaDeAlertas = {}): Promise<Pagina<Alerta>> {
  return request<Pagina<Alerta>>("/alerts/", { query: consulta });
}

/**
 * Alertas nascem do job Celery, nunca de um POST — só existem duas transições.
 *
 * `read` marca como lido e carimba `read_at`; `dismiss` tira da caixa de
 * entrada sem apagar o histórico.
 */
export function marcarComoLido(id: string): Promise<Alerta> {
  return request<Alerta>(`/alerts/${id}/read/`, { method: "POST" });
}

export function descartar(id: string): Promise<Alerta> {
  return request<Alerta>(`/alerts/${id}/dismiss/`, { method: "POST" });
}

// ------------------------------------------------------------------ regras

export type CanalDeAlerta = "in_app" | "email";

export type DadosDeRegra = {
  offset_days: number;
  channel?: CanalDeAlerta;
  is_active?: boolean;
};

export function listarRegras(tabelaId: string): Promise<Pagina<RegraDeAlerta>> {
  return request<Pagina<RegraDeAlerta>>(`/tables/${tabelaId}/alert-rules/`);
}

/**
 * `channel` passou a ser enviado na Phase 5.
 *
 * Antes era omitido de propósito: a entrega por e-mail não existia, e deixar o
 * usuário escolher `email` criaria uma regra que não dispara nada, em silêncio.
 * Agora `alerts.send_pending_emails` entrega de verdade, então a escolha
 * corresponde a um comportamento real.
 *
 * Omitir continua válido — o default do modelo é `in_app`.
 */
export function criarRegra(
  tabelaId: string,
  dados: DadosDeRegra,
): Promise<RegraDeAlerta> {
  return request<RegraDeAlerta>(`/tables/${tabelaId}/alert-rules/`, {
    method: "POST",
    body: dados,
  });
}

export function atualizarRegra(
  tabelaId: string,
  regraId: string,
  dados: Partial<DadosDeRegra>,
): Promise<RegraDeAlerta> {
  return request<RegraDeAlerta>(`/tables/${tabelaId}/alert-rules/${regraId}/`, {
    method: "PATCH",
    body: dados,
  });
}

export function excluirRegra(tabelaId: string, regraId: string): Promise<void> {
  return request<void>(`/tables/${tabelaId}/alert-rules/${regraId}/`, {
    method: "DELETE",
  });
}
