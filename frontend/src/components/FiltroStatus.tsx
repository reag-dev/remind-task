import { useState } from "react";

import { DUE_STATUS, ROTULO_DUE_STATUS, type DueStatus } from "../api/tipos.ts";

type Props = {
  selecionados: string[];
  ate: string | null;
  de: string | null;
  onStatus: (status: string[]) => void;
  onIntervalo: (de: string | null, ate: string | null) => void;
};

export function FiltroStatus({ selecionados, ate, de, onStatus, onIntervalo }: Props) {
  function alternar(status: DueStatus) {
    onStatus(
      selecionados.includes(status)
        ? selecionados.filter((item) => item !== status)
        : [...selecionados, status],
    );
  }

  const temFiltro = selecionados.length > 0 || ate !== null || de !== null;

  // Aberto de saída quando a URL já chega com filtro (voltar, link colado).
  // Depois disso é o usuário quem decide — fechar sozinho ao limpar os
  // filtros escondería o painel debaixo de quem ainda está olhando para ele.
  const [expandido, setExpandido] = useState(temFiltro);

  if (!expandido) {
    return (
      <button
        type="button"
        className="secundario"
        aria-expanded="false"
        onClick={() => setExpandido(true)}
      >
        Filtros{temFiltro ? ` (${selecionados.length + (de !== null || ate !== null ? 1 : 0)})` : ""}
      </button>
    );
  }

  return (
    <section className="filtros" aria-label="Filtros">
      <div className="titulo-com-acao">
        <span className="sutil">Filtros</span>
        <button
          type="button"
          className="ligacao"
          aria-expanded="true"
          onClick={() => setExpandido(false)}
        >
          Ocultar
        </button>
      </div>

      {/* `group` e não uma lista de checkboxes soltos: um leitor de tela anuncia
          "Status, grupo" e depois cada opção, em vez de cinco caixas sem
          contexto no meio da página. */}
      <div role="group" aria-label="Status" className="filtro-status">
        {DUE_STATUS.map((status) => {
          const ativo = selecionados.includes(status);
          return (
            <button
              key={status}
              type="button"
              className={`filtro-chip${ativo ? " ativo" : ""}`}
              aria-pressed={ativo}
              onClick={() => alternar(status)}
            >
              {ROTULO_DUE_STATUS[status]}
            </button>
          );
        })}
      </div>

      <div className="filtro-datas">
        <label htmlFor="vence-de" className="sutil">
          Vence de
        </label>
        <input
          id="vence-de"
          type="date"
          value={de ?? ""}
          onChange={(evento) => onIntervalo(evento.target.value || null, ate)}
        />
        <label htmlFor="vence-ate" className="sutil">
          até
        </label>
        <input
          id="vence-ate"
          type="date"
          value={ate ?? ""}
          onChange={(evento) => onIntervalo(de, evento.target.value || null)}
        />

        {temFiltro && (
          <button
            type="button"
            className="ligacao"
            onClick={() => {
              onStatus([]);
              onIntervalo(null, null);
            }}
          >
            Limpar filtros
          </button>
        )}
      </div>
    </section>
  );
}
