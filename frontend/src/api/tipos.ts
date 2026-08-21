/**
 * Tipos do domínio, derivados do schema gerado.
 *
 * `schema.d.ts` é gerado por `npm run api:types` e não se edita à mão — o que
 * estiver errado lá se conserta no backend. Este arquivo faz três coisas que o
 * gerador não tem como fazer sozinho:
 *
 * 1. Dá nomes de domínio aos tipos (`Registro`, e não `components["schemas"]["Record"]`).
 * 2. Estreita `data`, que o drf-spectacular só sabe descrever como `unknown`.
 * 3. Escreve à mão o `DueStatus`, que o schema perde. Ver a nota abaixo.
 */

import type { components } from "./schema.d.ts";

type Schemas = components["schemas"];

/**
 * `Record` é o nome do recurso no backend E o nome de um utilitário embutido do
 * TypeScript. Importar o primeiro apagaria o segundo dentro de cada arquivo que
 * o usasse — e `Record<string, unknown>` aparece justamente na linha ao lado,
 * em `DadosDoRegistro`. Fica `Registro`, em português como o resto do domínio.
 */
export type Registro = Omit<Schemas["Record"], "data"> & {
  data?: DadosDoRegistro;
};

/**
 * `columns` reapontado para o `Coluna` estreitado.
 *
 * O detalhe da tabela traz as colunas embutidas, e sem esta substituição elas
 * chegariam com o `options: unknown` do schema cru — o mesmo tipo teria duas
 * formas dependendo de por onde veio, e só uma delas serviria aos componentes.
 */
export type Tabela = Omit<Schemas["Table"], "columns"> & {
  readonly columns: Coluna[];
};

/**
 * `options` estreitado para `string[]`.
 *
 * O schema diz `unknown` porque no backend é um `JSONField`, e o
 * drf-spectacular não infere forma de JSON livre. Mas aqui — diferente do
 * `data` do registro — a forma **é** garantida: `ColumnSerializer.validate_options`
 * recusa qualquer coisa que não seja lista, exige texto não vazio em cada item
 * e rejeita repetidos. O default do modelo é `list`, então o campo nunca é
 * nulo, só ausente na resposta quando vazio.
 *
 * Ou seja: a garantia existe, só não está no schema. Estreitar aqui é registrar
 * um fato do backend, não torcer para que seja verdade.
 */
export type Coluna = Omit<Schemas["Column"], "options"> & {
  options?: string[];
};
export type Alerta = Schemas["Alert"];
export type RegraDeAlerta = Schemas["AlertRule"];
export type Usuario = Schemas["User"];

export type TipoDeColuna = Schemas["TypeEnum"];
export type StatusDeAlerta = Schemas["StatusEnum"];

/**
 * O JSONB de `records.data`, chaveado pelo `key` da coluna — nunca pelo `name`.
 *
 * O schema diz `unknown` porque o campo é um `JSONField` sem forma fixa: a
 * forma é a definição de colunas da tabela, que só existe em tempo de execução.
 * `unknown` é honesto e é o que força cada leitura a passar por `CelulaValor`,
 * onde o tipo da coluna decide como interpretar o valor.
 */
export type DadosDoRegistro = Record<string, unknown>;

/**
 * Estados de vencimento (RF10).
 *
 * ATENÇÃO: esta união é escrita à mão, e o schema **não** a protege.
 * `RecordSerializer.get_due_status` é um `SerializerMethodField`, e o
 * drf-spectacular não consegue inferir escolhas de um método — o schema gerado
 * traz `due_status: string`, com os cinco valores apenas em prosa no
 * `help_text`. Compare com `TypeEnum` e `StatusEnum`, que saem como união
 * porque nascem de `choices` de campo de modelo.
 *
 * Consequência prática: se o backend acrescentar um sexto status, nada aqui
 * quebra na compilação. `ehDueStatus` existe para que a divergência apareça em
 * runtime, no ponto de entrada, em vez de virar uma célula em branco no meio do
 * grid.
 */
export const DUE_STATUS = [
  "overdue",
  "due_today",
  "due_soon",
  "on_track",
  "no_due",
] as const;

export type DueStatus = (typeof DUE_STATUS)[number];

export function ehDueStatus(valor: string): valor is DueStatus {
  return (DUE_STATUS as readonly string[]).includes(valor);
}

/** Rótulos em pt-BR, iguais aos de `records/status.py`. */
export const ROTULO_DUE_STATUS: Record<DueStatus, string> = {
  overdue: "Vencido",
  due_today: "Vence hoje",
  due_soon: "Próximo do vencimento",
  on_track: "Em dia",
  no_due: "Sem vencimento",
};

/**
 * Tipos de coluna, na ordem em que aparecem no seletor.
 *
 * `due_date` fica por último de propósito: é o tipo com regra especial (no
 * máximo um por tabela) e o que muda o comportamento da tabela inteira.
 *
 * Diferente de `DueStatus`, esta união **vem do schema** (`TypeEnum`), porque
 * nasce de `choices` de campo de modelo. Se o backend acrescentar um tipo, o
 * `Record<TipoDeColuna, string>` abaixo passa a faltar uma chave e a
 * compilação quebra aqui — que é onde deve quebrar.
 */
export const TIPOS_DE_COLUNA: readonly TipoDeColuna[] = [
  "text",
  "number",
  "date",
  "datetime",
  "boolean",
  "email",
  "select",
  "due_date",
];

/** Rótulos iguais aos do `ColumnType` em `tables/models.py`. */
export const ROTULO_TIPO: Record<TipoDeColuna, string> = {
  text: "Texto",
  number: "Número",
  date: "Data",
  datetime: "Data e hora",
  boolean: "Booleano",
  email: "E-mail",
  select: "Lista de opções",
  due_date: "Data de vencimento",
};
