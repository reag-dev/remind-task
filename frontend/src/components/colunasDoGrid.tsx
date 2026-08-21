import { createColumnHelper, tableFeatures } from "@tanstack/react-table";

import type { Coluna, Registro } from "../api/tipos.ts";
import { CelulaValor } from "./CelulaValor.tsx";
import { SeloStatus } from "./SeloStatus.tsx";

/**
 * As features da tabela — e o que ficou de fora é o ponto.
 *
 * O TanStack Table v9 exige declarar cada feature explicitamente. Aqui não
 * entram `rowPaginationFeature` nem `rowSortingFeature`, e isso não é economia:
 * é a garantia estrutural contra a armadilha 8 do plano.
 *
 * Este backend pagina, ordena e filtra no Postgres. Uma tabela que também
 * paginasse do lado do cliente estaria paginando **as 50 linhas que estão na
 * memória** — o rodapé diria "página 1 de 1" com 137 registros no banco, e
 * ordenar por vencimento reordenaria um recorte arbitrário. Nada seria
 * lançado.
 *
 * No v8 isso se evitava lembrando de passar `manualPagination: true`, uma flag
 * que um autocomplete distraído reverte. No v9 a feature simplesmente não
 * existe na instância: não há `table.getState().pagination` para ler errado. A
 * Phase 5 opta pelas features de servidor de forma deliberada.
 */
export const recursosDoGrid = tableFeatures({});

const helper = createColumnHelper<typeof recursosDoGrid, Registro>();

/**
 * Monta as colunas do grid a partir da definição da tabela.
 *
 * As colunas são dado de runtime, não código: vêm de `table.columns`, já na
 * ordem de `position` — é por isso que um `columnHelper` cabe melhor aqui do
 * que um array literal.
 */
export function montarColunas(
  colunas: Coluna[],
  acoes: {
    onEditar: (registro: Registro) => void;
    onExcluir: (registro: Registro) => void;
  },
) {
  return [
    // Status primeiro, antes das colunas do usuário. A pergunta que traz alguém
    // a esta tela é "o que está vencendo" — a resposta não deve exigir rolagem
    // horizontal até a última coluna.
    helper.display({
      id: "status",
      header: "Status",
      cell: ({ row }) => (
        <SeloStatus status={row.original.due_status} dias={row.original.days_until_due} />
      ),
    }),

    ...colunas.map((coluna) =>
      helper.accessor(
        // `data[key]`, não `data[name]`: o JSONB é indexado pelo slug, e o
        // `name` é só o rótulo, que muda quando o usuário renomeia a coluna.
        (registro: Registro) => registro.data?.[coluna.key],
        {
          id: coluna.key,
          header: coluna.name,
          cell: (info) => (
            <CelulaValor
              tipo={coluna.type}
              valor={info.getValue()}
              sensivel={coluna.is_sensitive ?? false}
              rotulo={coluna.name}
            />
          ),
        },
      ),
    ),

    helper.display({
      id: "acoes",
      header: "",
      cell: ({ row }) => (
        <div className="acoes">
          <button
            type="button"
            className="secundario"
            onClick={() => acoes.onEditar(row.original)}
          >
            Editar
          </button>
          <button
            type="button"
            className="destrutivo"
            onClick={() => acoes.onExcluir(row.original)}
          >
            Excluir
          </button>
        </div>
      ),
    }),
  ];
}
