import { useState } from "react";

import { baixarCsv, DELIMITADORES, type FiltrosDeExportacao } from "../api/export.ts";

type Props = {
  tabelaId: string;
  /**
   * Os MESMOS filtros da tela.
   *
   * É o que a docstring de `RecordViewSet.export` promete (RS08): a exportação
   * não tem caminho de consulta próprio, ela reusa a queryset da listagem. Uma
   * UI que exportasse ignorando o filtro visível seria mentira — o usuário
   * filtra os vencidos, clica em exportar e recebe a tabela inteira.
   */
  filtros: FiltrosDeExportacao;
  /** Quantas linhas o filtro atual seleciona, para o botão dizer o que vai sair. */
  total: number;
};

export function BotaoExportar({ tabelaId, filtros, total }: Props) {
  const [delimitador, setDelimitador] = useState<string>(",");
  const [baixando, setBaixando] = useState(false);
  const [erro, setErro] = useState(false);

  async function exportar() {
    setErro(false);
    setBaixando(true);
    try {
      await baixarCsv(tabelaId, filtros, delimitador);
    } catch {
      setErro(true);
    } finally {
      setBaixando(false);
    }
  }

  return (
    <div className="exportar">
      <label htmlFor="delimitador" className="sutil">
        Separador
      </label>
      <select
        id="delimitador"
        value={delimitador}
        onChange={(evento) => setDelimitador(evento.target.value)}
      >
        {DELIMITADORES.map((opcao) => (
          <option key={opcao.valor} value={opcao.valor}>
            {opcao.rotulo}
          </option>
        ))}
      </select>

      <button
        type="button"
        className="secundario"
        disabled={baixando || total === 0}
        onClick={() => void exportar()}
      >
        {/* A resposta é streaming e pode demorar num arquivo grande; sem o
            estado de espera o usuário clicaria de novo achando que falhou. */}
        {baixando ? "Gerando…" : `Exportar ${total} em CSV`}
      </button>

      {erro && (
        <p className="erro" role="alert">
          Não foi possível gerar o arquivo. Tente novamente.
        </p>
      )}
    </div>
  );
}
