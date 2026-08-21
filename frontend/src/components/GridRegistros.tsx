import { useTable } from "@tanstack/react-table";
import { useMemo } from "react";

import type { Coluna, Registro } from "../api/tipos.ts";
import type { CampoOrdenavel, Ordenacao } from "../hooks/useTabelaServidor.ts";
import { montarColunas, recursosDoGrid } from "./colunasDoGrid.tsx";

type Props = {
  colunas: Coluna[];
  registros: Registro[];
  /** Há filtro ativo — muda a mensagem de lista vazia. */
  comFiltro: boolean;
  ordenacao: Ordenacao;
  onOrdenar: (campo: CampoOrdenavel) => void;
  onEditar: (registro: Registro) => void;
  onExcluir: (registro: Registro) => void;
};

/**
 * Quais colunas do grid são clicáveis para ordenar.
 *
 * O backend só ordena por `ordering_fields` — nenhuma coluna dinâmica do JSONB
 * está lá. Um cabeçalho clicável que produzisse `?ordering=cliente` geraria uma
 * requisição que o servidor ignora: a tabela não mudaria e pareceria bug.
 *
 * O selo de status e a coluna de vencimento apontam para o mesmo campo, porque
 * o status É derivado do vencimento — ordenar por um é ordenar pelo outro.
 */
function mapaDeOrdenacao(colunas: Coluna[]): Record<string, CampoOrdenavel> {
  const mapa: Record<string, CampoOrdenavel> = { status: "due_date" };
  for (const coluna of colunas) {
    if (coluna.type === "due_date") mapa[coluna.key] = "due_date";
  }
  return mapa;
}

export function GridRegistros({
  colunas,
  registros,
  comFiltro,
  ordenacao,
  onOrdenar,
  onEditar,
  onExcluir,
}: Props) {
  // `useMemo` obrigatório: `montarColunas` cria definições novas a cada render,
  // e a tabela trata identidade de coluna por referência — sem isto ela
  // remontaria o modelo inteiro a cada digitação em qualquer campo da tela.
  const definicoes = useMemo(
    () => montarColunas(colunas, { onEditar, onExcluir }),
    [colunas, onEditar, onExcluir],
  );

  const ordenaveis = useMemo(() => mapaDeOrdenacao(colunas), [colunas]);

  const tabela = useTable({
    features: recursosDoGrid,
    columns: definicoes,
    data: registros,
  });

  if (registros.length === 0) {
    // A distinção importa: "não há nada" pede criar o primeiro registro,
    // "nada casou" pede afrouxar o filtro. A mesma frase para os dois casos
    // manda o usuário para a ação errada na metade das vezes.
    return (
      <p className="vazio">
        {comFiltro
          ? "Nenhum registro corresponde aos filtros aplicados."
          : "Nenhum registro nesta tabela ainda."}
      </p>
    );
  }

  return (
    <div className="rolagem-horizontal">
      <table className="grid">
        <thead>
          {tabela.getHeaderGroups().map((grupo) => (
            <tr key={grupo.id}>
              {grupo.headers.map((cabecalho) => {
                const campo = ordenaveis[cabecalho.column.id];
                const ativo = campo !== undefined && ordenacao.campo === campo;

                return (
                  <th
                    key={cabecalho.id}
                    scope="col"
                    // `aria-sort` é o que um leitor de tela usa para anunciar a
                    // ordenação. A setinha visual não diz nada para quem não vê.
                    aria-sort={
                      ativo
                        ? ordenacao.descendente
                          ? "descending"
                          : "ascending"
                        : undefined
                    }
                  >
                    {campo === undefined ? (
                      <tabela.FlexRender header={cabecalho} />
                    ) : (
                      <button
                        type="button"
                        className="ligacao cabecalho-ordenavel"
                        onClick={() => onOrdenar(campo)}
                      >
                        <tabela.FlexRender header={cabecalho} />
                        <span aria-hidden="true">
                          {ativo ? (ordenacao.descendente ? " ↓" : " ↑") : " ↕"}
                        </span>
                      </button>
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {tabela.getRowModel().rows.map((linha) => (
            <tr key={linha.id}>
              {/* `getAllCells`, nao `getVisibleCells`: este ultimo pertence a
                  columnVisibilityFeature, que nao foi declarada em
                  `recursosDoGrid`. O v9 nao expoe o metodo, e o erro aparece
                  na compilacao em vez de virar undefined em runtime. */}
              {linha.getAllCells().map((celula) => (
                <td key={celula.id}>
                  <tabela.FlexRender cell={celula} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
