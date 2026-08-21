/**
 * Formatação de valores, em funções puras.
 *
 * Separado dos componentes de propósito: aqui estão as regras que dão errado em
 * silêncio (fuso, `[object Object]`), e elas merecem teste próprio, sem montar
 * árvore de React para exercitá-las.
 */

const NUMERO = new Intl.NumberFormat("pt-BR");

/**
 * Converte um valor do JSONB para texto sem produzir `[object Object]`.
 *
 * O `data` é `Record<string, unknown>` porque a forma dele só existe em tempo
 * de execução. Na prática o validador do backend garante que uma coluna `text`
 * guarda texto — mas "na prática" não é garantia de tipo, e um registro gravado
 * antes de a coluna existir chegaria aqui como objeto. `[object Object]` numa
 * célula esconde o problema; o JSON mostra o que realmente está gravado.
 */
export function paraTexto(valor: unknown): string {
  if (typeof valor === "string") return valor;
  if (typeof valor === "number" || typeof valor === "boolean") return String(valor);
  return JSON.stringify(valor) ?? "";
}

export function formatarNumero(valor: unknown): string {
  return typeof valor === "number" ? NUMERO.format(valor) : paraTexto(valor);
}

/**
 * Formata `YYYY-MM-DD` sem passar por `Date`.
 *
 * `new Date("2026-08-20")` é interpretado como **meia-noite UTC**, e qualquer
 * formatação num fuso a oeste de Greenwich devolve o dia anterior — em
 * America/Sao_Paulo (UTC-3) o vencimento de 20/08 apareceria como 19/08. É o
 * bug clássico de data em JavaScript, e aqui seria grave: a coluna de
 * vencimento é o motivo do produto existir.
 *
 * O backend manda a data como texto puro, sem hora e sem fuso, exatamente para
 * não haver conversão. Fatiar a string honra isso.
 */
export function formatarData(valor: string): string {
  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(valor);
  if (!partes) return valor;
  const [, ano, mes, dia] = partes;
  return `${dia}/${mes}/${ano}`;
}

/**
 * `datetime` é o oposto de `date`: tem instante e fuso, então **deve** ser
 * convertido para o fuso de quem lê. Aqui `Date` é a ferramenta certa.
 */
export function formatarDataHora(valor: string): string {
  const data = new Date(valor);
  return Number.isNaN(data.getTime()) ? valor : data.toLocaleString("pt-BR");
}

/** Texto relativo de dias, para acompanhar o selo de status. */
export function textoDeDias(dias: number): string {
  if (dias === 0) return "hoje";
  if (dias === 1) return "amanhã";
  if (dias === -1) return "ontem";
  if (dias < 0) return `há ${Math.abs(dias)} dias`;
  return `em ${dias} dias`;
}
