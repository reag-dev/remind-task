import { TAMANHOS_DE_PAGINA } from "../hooks/useTabelaServidor.ts";

type Props = {
  pagina: number;
  tamanho: number;
  total: number;
  /** Quantos itens vieram nesta página — pode ser menos que `tamanho` na última. */
  nesta: number;
  onPagina: (pagina: number) => void;
  onTamanho: (tamanho: number) => void;
};

export function Paginacao({ pagina, tamanho, total, nesta, onPagina, onTamanho }: Props) {
  // Derivado de `count`, e não recebido pronto: mandar `pageCount` e `rowCount`
  // separados abre espaço para os dois discordarem.
  const paginas = Math.max(1, Math.ceil(total / tamanho));
  const primeiro = total === 0 ? 0 : (pagina - 1) * tamanho + 1;
  const ultimo = total === 0 ? 0 : primeiro + nesta - 1;

  return (
    <nav className="paginacao" aria-label="Paginação">
      {/* `aria-live` porque a troca de página muda a tabela inteira sem mover o
          foco: quem usa leitor de tela não teria como saber que algo mudou. */}
      <p className="sutil" aria-live="polite">
        {total === 0
          ? "Nenhum registro"
          : `${primeiro}–${ultimo} de ${total} registro${total === 1 ? "" : "s"}`}
      </p>

      <div className="paginacao-controles">
        <label htmlFor="tamanho-pagina" className="sutil">
          Por página
        </label>
        <select
          id="tamanho-pagina"
          value={tamanho}
          onChange={(evento) => onTamanho(Number(evento.target.value))}
        >
          {TAMANHOS_DE_PAGINA.map((opcao) => (
            <option key={opcao} value={opcao}>
              {opcao}
            </option>
          ))}
        </select>

        <button
          type="button"
          className="secundario"
          disabled={pagina <= 1}
          onClick={() => onPagina(pagina - 1)}
        >
          Anterior
        </button>
        <span className="sutil">
          {pagina} de {paginas}
        </span>
        <button
          type="button"
          className="secundario"
          disabled={pagina >= paginas}
          onClick={() => onPagina(pagina + 1)}
        >
          Próxima
        </button>
      </div>
    </nav>
  );
}
