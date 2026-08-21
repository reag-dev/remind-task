import { useState } from "react";

import type { TipoDeColuna } from "../api/tipos.ts";
import { formatarData, formatarDataHora, formatarNumero, paraTexto } from "../formato.ts";

function Conteudo({ tipo, valor }: { tipo: TipoDeColuna; valor: unknown }) {
  // `null`, ausente e string vazia são a mesma coisa para quem lê: célula
  // vazia. Um traço é mais legível que espaço em branco.
  if (valor === null || valor === undefined || valor === "") {
    return <span className="sutil">—</span>;
  }

  switch (tipo) {
    case "boolean":
      return valor ? <span aria-label="sim">✓</span> : <span aria-label="não">✗</span>;

    case "number":
      return <>{formatarNumero(valor)}</>;

    case "date":
    case "due_date":
      return <>{formatarData(paraTexto(valor))}</>;

    case "datetime":
      return <>{formatarDataHora(paraTexto(valor))}</>;

    case "email":
      return <a href={`mailto:${paraTexto(valor)}`}>{paraTexto(valor)}</a>;

    case "select":
      return <span className="chip">{paraTexto(valor)}</span>;

    case "text":
      return <>{paraTexto(valor)}</>;
  }
}

type Props = {
  tipo: TipoDeColuna;
  valor: unknown;
  sensivel: boolean;
  /** Rótulo da coluna, para o botão de revelar dizer o que revela. */
  rotulo: string;
};

export function CelulaValor({ tipo, valor, sensivel, rotulo }: Props) {
  const [revelado, setRevelado] = useState(false);

  if (!sensivel) return <Conteudo tipo={tipo} valor={valor} />;

  // Célula vazia não tem o que esconder, e mascarar o traço faria parecer que
  // existe um valor guardado ali.
  if (valor === null || valor === undefined || valor === "") {
    return <span className="sutil">—</span>;
  }

  if (!revelado) {
    return (
      <button
        type="button"
        className="ligacao mascara"
        // O estado de revelado vive AQUI, no componente da célula. Trocar de
        // página desmonta a linha e o valor volta a ficar escondido — que é o
        // comportamento certo para RS05: revelar é um ato deliberado, não uma
        // preferência que gruda na sessão.
        onClick={() => setRevelado(true)}
        aria-label={`Revelar ${rotulo}`}
      >
        ••••••
      </button>
    );
  }

  return (
    <span className="revelado">
      <Conteudo tipo={tipo} valor={valor} />{" "}
      <button
        type="button"
        className="ligacao"
        onClick={() => setRevelado(false)}
        aria-label={`Ocultar ${rotulo}`}
      >
        ocultar
      </button>
    </span>
  );
}
