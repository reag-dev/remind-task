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

  return (
    <section className="filtros" aria-label="Filtros">
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
