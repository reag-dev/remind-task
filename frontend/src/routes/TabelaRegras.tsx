import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { atualizarRegra, criarRegra, excluirRegra, listarRegras } from "../api/alerts.ts";
import { ApiError } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import { atualizarTabela, obterTabela } from "../api/tables.ts";
import type { RegraDeAlerta } from "../api/tipos.ts";

/** `OFFSET_LIMIT` do backend (`alerts/models.py`). */
const LIMITE = 365;

export function TabelaRegras() {
  const { id = "" } = useParams();

  const tabela = useQuery({
    queryKey: chaves.tabela(id),
    queryFn: () => obterTabela(id),
  });
  const regras = useQuery({
    queryKey: chaves.regras(id),
    queryFn: () => listarRegras(id),
  });

  if (tabela.isPending || regras.isPending) return <p className="sutil">Carregando…</p>;

  if (tabela.isError || regras.isError) {
    const erro = tabela.error ?? regras.error;
    const naoEncontrada = erro instanceof ApiError && erro.status === 404;
    return (
      <p className={naoEncontrada ? "vazio" : "erro"} role="alert">
        {naoEncontrada
          ? "Tabela não encontrada."
          : "Não foi possível carregar as regras."}{" "}
        <Link to="/">Voltar para suas tabelas</Link>
      </p>
    );
  }

  return (
    <>
      <p className="sutil">
        <Link to={`/tabelas/${id}`}>← {tabela.data.name}</Link>
      </p>
      <h1>Alertas desta tabela</h1>

      {/* Os dois conceitos lado a lado, com a diferença explícita. Eles são
          confundidos o tempo todo porque ambos se chamam "antecedência" — e a
          consequência de confundir é real: mexer no limiar visual achando que
          se está mexendo no disparo da notificação. */}
      <LimiarVisual tabelaId={id} valor={tabela.data.alert_lead_days ?? 3} />
      <Regras tabelaId={id} regras={regras.data.results} />
    </>
  );
}

function LimiarVisual({ tabelaId, valor }: { tabelaId: string; valor: number }) {
  const cliente = useQueryClient();
  const [dias, setDias] = useState(String(valor));

  const salvar = useMutation({
    mutationFn: () => atualizarTabela(tabelaId, { alert_lead_days: Number(dias) }),
    onSuccess: async () => {
      await cliente.invalidateQueries({ queryKey: chaves.tabela(tabelaId) });
    },
  });

  return (
    <section className="cartao">
      <h2>Indicador visual</h2>
      <p className="sutil">
        Quantos dias antes do vencimento um registro passa a aparecer como{" "}
        <strong>próximo do vencimento</strong> no grid. Muda só a cor e o rótulo na
        listagem — <strong>não gera notificação</strong>.
      </p>
      <form
        className="formulario-inline"
        onSubmit={(evento) => {
          evento.preventDefault();
          salvar.mutate();
        }}
      >
        <label htmlFor="limiar" className="oculto-visual">
          Dias de antecedência do indicador
        </label>
        <input
          id="limiar"
          type="number"
          min={0}
          max={LIMITE}
          value={dias}
          onChange={(evento) => setDias(evento.target.value)}
        />
        <button type="submit" disabled={salvar.isPending || dias === String(valor)}>
          {salvar.isPending ? "Salvando…" : "Salvar"}
        </button>
        {salvar.isError && (
          <p className="erro" role="alert">
            Não foi possível salvar.
          </p>
        )}
      </form>
    </section>
  );
}

function Regras({ tabelaId, regras }: { tabelaId: string; regras: RegraDeAlerta[] }) {
  const cliente = useQueryClient();
  const [novo, setNovo] = useState("");

  async function recarregar() {
    await Promise.all([
      cliente.invalidateQueries({ queryKey: chaves.regras(tabelaId) }),
      // Regra nova pode gerar alertas na próxima execução do job; a inbox
      // continua válida agora, mas a contagem muda depois.
      cliente.invalidateQueries({ queryKey: chaves.alertas }),
    ]);
  }

  const criar = useMutation({
    mutationFn: () => criarRegra(tabelaId, { offset_days: Number(novo) }),
    onSuccess: async () => {
      await recarregar();
      setNovo("");
    },
  });

  const erro = criar.error instanceof ApiError ? criar.error : null;

  return (
    <section className="cartao">
      <h2>Regras de notificação</h2>
      <p className="sutil">
        Cada regra gera um alerta na caixa de entrada. Antecedência em dias:{" "}
        <strong>3</strong> avisa três dias antes, <strong>0</strong> avisa no dia, e{" "}
        <strong>-1</strong> avisa um dia depois — útil para cobrar atraso.
      </p>

      {regras.length === 0 ? (
        <p className="vazio">
          Sem regras: nenhum alerta será gerado para os vencimentos desta tabela.
        </p>
      ) : (
        <ul className="lista-regras">
          {regras.map((regra) => (
            <LinhaDeRegra
              key={regra.id}
              tabelaId={tabelaId}
              regra={regra}
              onMudou={recarregar}
            />
          ))}
        </ul>
      )}

      <form
        className="formulario-inline"
        onSubmit={(evento) => {
          evento.preventDefault();
          criar.mutate();
        }}
      >
        <label htmlFor="nova-regra">Nova regra (dias)</label>
        <input
          id="nova-regra"
          type="number"
          min={-LIMITE}
          max={LIMITE}
          value={novo}
          onChange={(evento) => setNovo(evento.target.value)}
        />
        <button type="submit" disabled={criar.isPending || novo === ""}>
          Adicionar
        </button>
      </form>

      {erro?.status === 400 && (
        <p className="erro" role="alert">
          {/* A unicidade é garantida por `alert_rules_unique` no banco; a
              mensagem vem pronta do serializer. */}
          {erro.campo("non_field_errors")[0] ??
            erro.campo("offset_days")[0] ??
            erro.corpo.detail ??
            "Não foi possível criar a regra."}
        </p>
      )}
    </section>
  );
}

function LinhaDeRegra({
  tabelaId,
  regra,
  onMudou,
}: {
  tabelaId: string;
  regra: RegraDeAlerta;
  onMudou: () => Promise<void>;
}) {
  const alternar = useMutation({
    mutationFn: () =>
      atualizarRegra(tabelaId, regra.id, { is_active: !(regra.is_active ?? true) }),
    onSuccess: onMudou,
  });
  const remover = useMutation({
    mutationFn: () => excluirRegra(tabelaId, regra.id),
    onSuccess: onMudou,
  });

  const ativa = regra.is_active ?? true;

  return (
    <li className="linha-regra">
      <span>{descrever(regra.offset_days)}</span>
      {!ativa && <span className="sutil">· desativada</span>}
      <div className="acoes">
        <button
          type="button"
          className="secundario"
          disabled={alternar.isPending}
          onClick={() => alternar.mutate()}
        >
          {ativa ? "Desativar" : "Ativar"}
        </button>
        <button
          type="button"
          className="destrutivo"
          disabled={remover.isPending}
          onClick={() => remover.mutate()}
        >
          Remover
        </button>
      </div>
      {remover.isError && (
        <p className="erro" role="alert">
          {/* Apagar a regra apaga os alertas gerados por ela (cascata no
              banco). O 204 é o caminho normal; o erro aqui é rede ou 5xx. */}
          Não foi possível remover.
        </p>
      )}
    </li>
  );
}

function descrever(dias: number): string {
  if (dias === 0) return "No dia do vencimento";
  if (dias > 0) return `${dias} dia${dias === 1 ? "" : "s"} antes do vencimento`;
  const atraso = Math.abs(dias);
  return `${atraso} dia${atraso === 1 ? "" : "s"} depois do vencimento`;
}
