/**
 * Download do CSV (RF13).
 *
 * Por que isto não é um `<a href>`
 * -------------------------------
 * A rota exige `Authorization: Bearer`, e âncora não carrega header. As saídas
 * comuns para esse problema são piores que o problema:
 *
 * - Token na query string (`?token=...`) o coloca no log do servidor, no
 *   histórico do browser e no `Referer` de qualquer link que a página abra.
 * - Trocar para cookie de sessão nesta rota criaria uma segunda forma de
 *   autenticar, e com ela a superfície de CSRF que o JWT evita.
 *
 * A saída correta é buscar com `fetch` e montar o download a partir do blob.
 */

import { API_URL, ApiError, requestRaw } from "./client.ts";

export const DELIMITADORES = [
  { valor: ",", rotulo: "Vírgula (,)" },
  { valor: ";", rotulo: "Ponto e vírgula (;) — Excel pt-BR" },
] as const;

/**
 * Lê o nome do arquivo do `Content-Disposition`.
 *
 * Só funciona porque o backend declara `CORS_EXPOSE_HEADERS`: numa resposta
 * cross-origin o browser esconde do JavaScript qualquer header fora dessa
 * lista. Sem ela, `resposta.headers.get(...)` devolve `null` — sem erro, sem
 * aviso — e o arquivo baixaria com o nome da URL.
 */
function nomeDoArquivo(resposta: Response, alternativo: string): string {
  const cabecalho = resposta.headers.get("Content-Disposition");
  if (!cabecalho) return alternativo;

  const casou = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cabecalho);
  return casou?.[1] ? decodeURIComponent(casou[1]) : alternativo;
}

/**
 * Filtros que valem na exportação.
 *
 * `page` e `page_size` ficam de fora **de propósito**: o export transmite a
 * queryset filtrada inteira, em streaming, sem paginar. Mandá-los escreveria na
 * URL uma intenção que o servidor ignora — e daria a impressão de que o arquivo
 * respeita a página aberta.
 */
export type FiltrosDeExportacao = {
  ordering?: string;
  status?: string;
  due_before?: string;
  due_after?: string;
};

export async function baixarCsv(
  tabelaId: string,
  filtros: FiltrosDeExportacao,
  delimitador: string,
): Promise<void> {
  const url = new URL(`${API_URL}/tables/${tabelaId}/records/export/`);
  for (const [chave, valor] of Object.entries({ ...filtros, delimiter: delimitador })) {
    if (valor) url.searchParams.set(chave, valor);
  }

  const resposta = await requestRaw(url);

  if (!resposta.ok) {
    throw new ApiError(resposta.status, { detail: await resposta.text() });
  }

  const blob = await resposta.blob();
  const endereco = URL.createObjectURL(blob);

  try {
    const ancora = document.createElement("a");
    ancora.href = endereco;
    ancora.download = nomeDoArquivo(resposta, "registros.csv");
    document.body.appendChild(ancora);
    ancora.click();
    ancora.remove();
  } finally {
    // Sem o revoke, o blob fica na memória da aba até ela fechar. Numa sessão
    // que exporta várias tabelas grandes isso vaza de verdade.
    URL.revokeObjectURL(endereco);
  }
}
