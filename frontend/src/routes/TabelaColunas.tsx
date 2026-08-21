import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client.ts";
import { listarColunas } from "../api/columns.ts";
import { chaves } from "../api/query.ts";
import { obterTabela } from "../api/tables.ts";
import type { Coluna } from "../api/tipos.ts";
import { FormularioColuna } from "../components/FormularioColuna.tsx";
import { ListaColunas } from "../components/ListaColunas.tsx";

type Edicao = { modo: "fechado" } | { modo: "nova" } | { modo: "editar"; coluna: Coluna };

export function TabelaColunas() {
  const { id = "" } = useParams();
  const [edicao, setEdicao] = useState<Edicao>({ modo: "fechado" });

  const tabela = useQuery({
    queryKey: chaves.tabela(id),
    queryFn: () => obterTabela(id),
  });
  const colunas = useQuery({
    queryKey: chaves.colunas(id),
    queryFn: () => listarColunas(id),
  });

  if (tabela.isPending || colunas.isPending) {
    return <p className="sutil">Carregando…</p>;
  }

  if (tabela.isError || colunas.isError) {
    const erro = tabela.error ?? colunas.error;
    const naoEncontrada = erro instanceof ApiError && erro.status === 404;

    return (
      <p className={naoEncontrada ? "vazio" : "erro"} role="alert">
        {naoEncontrada
          ? "Tabela não encontrada."
          : "Não foi possível carregar as colunas."}{" "}
        <Link to="/">Voltar para suas tabelas</Link>
      </p>
    );
  }

  const lista = colunas.data.results;
  const jaTemVencimento = lista.some((coluna) => coluna.type === "due_date");

  return (
    <>
      <p className="sutil">
        <Link to={`/tabelas/${id}`}>← {tabela.data.name}</Link>
      </p>

      <div className="titulo-com-acao">
        <h1>Colunas</h1>
        {edicao.modo === "fechado" && (
          <button
            type="button"
            className="botao"
            onClick={() => setEdicao({ modo: "nova" })}
          >
            Nova coluna
          </button>
        )}
      </div>

      {!jaTemVencimento && lista.length > 0 && (
        <p className="aviso">
          Esta tabela não tem coluna de vencimento. Sem ela não há indicadores de prazo
          nem alertas — que é o ponto do sistema.
        </p>
      )}

      {edicao.modo !== "fechado" && (
        <FormularioColuna
          // Trocar de "nova" para "editar", ou de uma coluna para outra, precisa
          // remontar o formulário: sem a key, o React reaproveita a instância e
          // o `useState` mantém os valores da coluna anterior.
          key={edicao.modo === "editar" ? edicao.coluna.id : "nova"}
          tabelaId={id}
          coluna={edicao.modo === "editar" ? edicao.coluna : undefined}
          jaTemVencimento={jaTemVencimento}
          onSair={() => setEdicao({ modo: "fechado" })}
        />
      )}

      <ListaColunas
        tabelaId={id}
        colunas={lista}
        onEditar={(coluna) => setEdicao({ modo: "editar", coluna })}
      />
    </>
  );
}
