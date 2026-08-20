import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { excluirColuna, reordenarColunas } from "../api/columns.ts";
import { chaves } from "../api/query.ts";
import { ROTULO_TIPO, type Coluna } from "../api/tipos.ts";
import { DialogoConfirmar } from "./DialogoConfirmar.tsx";

type Props = {
  tabelaId: string;
  colunas: Coluna[];
  onEditar: (coluna: Coluna) => void;
};

export function ListaColunas({ tabelaId, colunas, onEditar }: Props) {
  const cliente = useQueryClient();
  const [aExcluir, setAExcluir] = useState<Coluna | null>(null);

  async function invalidar() {
    await Promise.all([
      cliente.invalidateQueries({ queryKey: chaves.colunas(tabelaId) }),
      cliente.invalidateQueries({ queryKey: chaves.tabela(tabelaId) }),
    ]);
  }

  const reordenar = useMutation({
    mutationFn: (ordem: string[]) => reordenarColunas(tabelaId, ordem),
    onSuccess: invalidar,
  });

  /**
   * Troca a coluna de lugar com a vizinha e manda a lista INTEIRA.
   *
   * O endpoint não é "mova X para N": o `ReorderSerializer` compara o conjunto
   * recebido com o conjunto atual da tabela e recusa qualquer diferença. Mandar
   * só o par trocado devolveria 400.
   */
  function mover(indice: number, direcao: -1 | 1) {
    const destino = indice + direcao;
    if (destino < 0 || destino >= colunas.length) return;

    const ordem = colunas.map((coluna) => coluna.id);
    const atual = ordem[indice];
    const vizinho = ordem[destino];
    if (atual === undefined || vizinho === undefined) return;

    ordem[indice] = vizinho;
    ordem[destino] = atual;
    reordenar.mutate(ordem);
  }

  if (colunas.length === 0) {
    return (
      <p className="vazio">
        Esta tabela ainda não tem colunas. Sem ao menos uma, não é possível inserir
        registros.
      </p>
    );
  }

  return (
    <>
      <ol className="lista-colunas">
        {colunas.map((coluna, indice) => (
          <li key={coluna.id} className="linha-coluna">
            <div className="ordenar">
              <button
                type="button"
                className="secundario"
                disabled={indice === 0 || reordenar.isPending}
                aria-label={`Mover ${coluna.name} para cima`}
                onClick={() => mover(indice, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="secundario"
                disabled={indice === colunas.length - 1 || reordenar.isPending}
                aria-label={`Mover ${coluna.name} para baixo`}
                onClick={() => mover(indice, 1)}
              >
                ↓
              </button>
            </div>

            <div className="coluna-info">
              <strong>{coluna.name}</strong>
              <p className="sutil meta">
                {ROTULO_TIPO[coluna.type]}
                {coluna.is_required && " · obrigatória"}
                {coluna.is_sensitive && " · sensível"}
                {/* `key` é o que indexa o JSONB dos registros, e é imutável.
                    Mostrar ajuda quem cruza a tela com o CSV exportado, onde o
                    cabeçalho é o rótulo mas a chave interna é esta. */}
                {" · chave "}
                <code>{coluna.key}</code>
              </p>
              {coluna.type === "select" && coluna.options && (
                <p className="sutil meta">Opções: {coluna.options.join(", ")}</p>
              )}
            </div>

            <div className="acoes">
              <button
                type="button"
                className="secundario"
                onClick={() => onEditar(coluna)}
              >
                Editar
              </button>
              <button
                type="button"
                className="destrutivo"
                onClick={() => setAExcluir(coluna)}
              >
                Excluir
              </button>
            </div>
          </li>
        ))}
      </ol>

      {reordenar.isError && (
        <p className="erro" role="alert">
          Não foi possível reordenar as colunas.
        </p>
      )}

      {aExcluir && (
        <ConfirmarExclusaoDeColuna
          tabelaId={tabelaId}
          coluna={aExcluir}
          onFechar={() => setAExcluir(null)}
          onExcluido={invalidar}
        />
      )}
    </>
  );
}

function ConfirmarExclusaoDeColuna({
  tabelaId,
  coluna,
  onFechar,
  onExcluido,
}: {
  tabelaId: string;
  coluna: Coluna;
  onFechar: () => void;
  onExcluido: () => Promise<void>;
}) {
  const excluir = useMutation({
    mutationFn: () => excluirColuna(tabelaId, coluna.id),
    onSuccess: async () => {
      await onExcluido();
      onFechar();
    },
  });

  return (
    <DialogoConfirmar
      titulo="Excluir coluna"
      rotuloConfirmar="Excluir"
      confirmando={excluir.isPending}
      onConfirmar={() => excluir.mutate()}
      onCancelar={onFechar}
    >
      <p>
        Apagar <strong>{coluna.name}</strong> também apaga o valor dessa coluna em{" "}
        <strong>todos os registros</strong> da tabela. Não há como desfazer.
      </p>
      {coluna.type === "due_date" && (
        // O backend zera o `due_date` promovido junto com a coluna
        // (`purge_column_key(was_due_date=True)`). Sem isso o job de alertas
        // dispararia por um vencimento que não tem mais origem — e quem apaga
        // a coluna não imagina que está desligando os alertas da tabela.
        <p className="erro">
          Esta é a coluna de vencimento. Os registros perdem a data, a tabela deixa de
          ter indicadores de vencimento e nenhum alerta novo será gerado.
        </p>
      )}
      {excluir.isError && (
        <p className="erro" role="alert">
          Não foi possível excluir. Tente novamente.
        </p>
      )}
    </DialogoConfirmar>
  );
}
