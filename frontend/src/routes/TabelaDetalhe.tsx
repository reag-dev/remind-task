import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import { obterTabela } from "../api/tables.ts";

/**
 * Detalhe da tabela — esqueleto da Phase 2.
 *
 * A Phase 3 acrescenta a gestão de colunas e a Phase 4 o grid de registros.
 * O que já existe aqui é o que as duas vão precisar: a tabela carregada e o
 * tratamento de 404.
 */
export function TabelaDetalhe() {
  const { id = "" } = useParams();
  const consulta = useQuery({
    queryKey: chaves.tabela(id),
    queryFn: () => obterTabela(id),
  });

  if (consulta.isPending) return <p className="sutil">Carregando…</p>;

  if (consulta.isError) {
    // 404 é a resposta para tabela inexistente E para tabela de outro dono —
    // o backend não distingue de propósito (RS04), porque um 403 confirmaria a
    // existência do recurso. A mensagem aqui precisa respeitar isso: dizer
    // "sem permissão" reintroduziria na interface o vazamento que a API evita.
    const naoEncontrada =
      consulta.error instanceof ApiError && consulta.error.status === 404;

    return (
      <p className={naoEncontrada ? "vazio" : "erro"} role="alert">
        {naoEncontrada
          ? "Tabela não encontrada."
          : "Não foi possível carregar a tabela."}{" "}
        <Link to="/">Voltar para suas tabelas</Link>
      </p>
    );
  }

  const tabela = consulta.data;

  return (
    <>
      <div className="titulo-com-acao">
        <h1>{tabela.name}</h1>
        <Link to={`/tabelas/${tabela.id}/colunas`} className="botao">
          Colunas ({tabela.columns.length})
        </Link>
      </div>
      {tabela.description && <p className="sutil">{tabela.description}</p>}
      <p className="vazio">O grid de registros entra na Phase 4.</p>
    </>
  );
}
