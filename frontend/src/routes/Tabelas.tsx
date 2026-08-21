import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import { atualizarTabela, excluirTabela, listarTabelas } from "../api/tables.ts";
import type { Tabela } from "../api/tipos.ts";
import { DialogoConfirmar } from "../components/DialogoConfirmar.tsx";

export function Tabelas() {
  const consulta = useQuery({ queryKey: chaves.tabelas, queryFn: listarTabelas });
  const [aExcluir, setAExcluir] = useState<Tabela | null>(null);

  if (consulta.isPending) return <p className="sutil">Carregando tabelas…</p>;

  if (consulta.isError) {
    return (
      <p className="erro" role="alert">
        Não foi possível carregar suas tabelas.{" "}
        <button type="button" className="ligacao" onClick={() => void consulta.refetch()}>
          Tentar de novo
        </button>
      </p>
    );
  }

  const tabelas = consulta.data.results;

  return (
    <>
      <div className="titulo-com-acao">
        <h1>Suas tabelas</h1>
        <Link to="/tabelas/nova" className="botao">
          Nova tabela
        </Link>
      </div>

      {tabelas.length === 0 ? (
        <p className="vazio">
          Nenhuma tabela ainda. Crie a primeira para começar a acompanhar vencimentos.
        </p>
      ) : (
        <ul className="lista-tabelas">
          {tabelas.map((tabela) => (
            <LinhaDeTabela
              key={tabela.id}
              tabela={tabela}
              onExcluir={() => setAExcluir(tabela)}
            />
          ))}
        </ul>
      )}

      {aExcluir && (
        <ConfirmarExclusao tabela={aExcluir} onFechar={() => setAExcluir(null)} />
      )}
    </>
  );
}

function LinhaDeTabela({ tabela, onExcluir }: { tabela: Tabela; onExcluir: () => void }) {
  const [renomeando, setRenomeando] = useState(false);

  return (
    <li className="linha-tabela">
      {renomeando ? (
        <FormularioDeNome tabela={tabela} onSair={() => setRenomeando(false)} />
      ) : (
        <>
          <div>
            <Link to={`/tabelas/${tabela.id}`} className="nome-tabela">
              {tabela.name}
            </Link>
            {tabela.description && <p className="sutil">{tabela.description}</p>}
            <p className="sutil meta">
              {tabela.columns.length} {tabela.columns.length === 1 ? "coluna" : "colunas"}{" "}
              · alerta {tabela.alert_lead_days ?? 0}{" "}
              {(tabela.alert_lead_days ?? 0) === 1 ? "dia" : "dias"} antes
            </p>
          </div>
          <div className="acoes">
            <button
              type="button"
              className="secundario"
              onClick={() => setRenomeando(true)}
            >
              Renomear
            </button>
            <button type="button" className="destrutivo" onClick={onExcluir}>
              Excluir
            </button>
          </div>
        </>
      )}
    </li>
  );
}

function FormularioDeNome({ tabela, onSair }: { tabela: Tabela; onSair: () => void }) {
  const cliente = useQueryClient();
  const [nome, setNome] = useState(tabela.name);

  const renomear = useMutation({
    mutationFn: (novo: string) => atualizarTabela(tabela.id, { name: novo }),
    onSuccess: async () => {
      await cliente.invalidateQueries({ queryKey: chaves.tabelas });
      onSair();
    },
  });

  // O backend recusa nome repetido com 400 e mensagem pronta
  // ("Você já tem uma tabela com esse nome."), garantido no banco por
  // `tables_unique_name_per_user`. Exibir a mensagem dele evita uma segunda
  // cópia da regra aqui, que sairia de sincronia.
  const erro =
    renomear.error instanceof ApiError
      ? (renomear.error.campo("name")[0] ?? renomear.error.message)
      : null;

  return (
    <form
      className="formulario-inline"
      onSubmit={(evento) => {
        evento.preventDefault();
        renomear.mutate(nome.trim());
      }}
    >
      <label htmlFor={`nome-${tabela.id}`} className="oculto-visual">
        Nome da tabela
      </label>
      <input
        id={`nome-${tabela.id}`}
        value={nome}
        autoFocus
        onChange={(evento) => setNome(evento.target.value)}
        onKeyDown={(evento) => evento.key === "Escape" && onSair()}
      />
      <button type="submit" disabled={renomear.isPending || !nome.trim()}>
        Salvar
      </button>
      <button type="button" className="secundario" onClick={onSair}>
        Cancelar
      </button>
      {erro && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
    </form>
  );
}

function ConfirmarExclusao({
  tabela,
  onFechar,
}: {
  tabela: Tabela;
  onFechar: () => void;
}) {
  const cliente = useQueryClient();
  const excluir = useMutation({
    mutationFn: () => excluirTabela(tabela.id),
    onSuccess: async () => {
      await cliente.invalidateQueries({ queryKey: chaves.tabelas });
      onFechar();
    },
  });

  return (
    <DialogoConfirmar
      titulo="Excluir tabela"
      rotuloConfirmar="Excluir"
      confirmando={excluir.isPending}
      onConfirmar={() => excluir.mutate()}
      onCancelar={onFechar}
    >
      {/* O nome vai no texto porque a exclusão é em cascata e irreversível:
          o backend leva junto colunas, registros, regras e alertas. Uma
          confirmação genérica ("tem certeza?") não deixa perceber que se
          clicou na linha errada. */}
      <p>
        Isto apaga <strong>{tabela.name}</strong> e tudo dentro dela —{" "}
        {tabela.columns.length} coluna(s), os registros e os alertas gerados. Não há como
        desfazer.
      </p>
      {excluir.isError && (
        <p className="erro" role="alert">
          Não foi possível excluir. Tente novamente.
        </p>
      )}
    </DialogoConfirmar>
  );
}
