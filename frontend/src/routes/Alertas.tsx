import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";

import { descartar, listarAlertas, marcarComoLido } from "../api/alerts.ts";
import type { Pagina } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import type { Alerta, StatusDeAlerta } from "../api/tipos.ts";
import { Paginacao } from "../components/Paginacao.tsx";
import { formatarData } from "../formato.ts";

/**
 * Filtros da caixa de entrada.
 *
 * `NAO_LIDO` é **`sent`**, não `pending` — e isso não é óbvio. O job cria
 * alertas `in_app` já como `sent`, porque "entregar no aplicativo" acontece no
 * ato de gravar a linha (ver `alerts.services`, `delivered_immediately`).
 * `pending` fica reservado para canais que dependem de confirmação de envio, e
 * hoje só existe o `in_app`. Filtrar por `pending` devolveria lista vazia
 * sempre — o pior tipo de filtro: o que parece funcionar.
 */
const ABAS = [
  { chave: "sent", rotulo: "Não lidos" },
  { chave: "read", rotulo: "Lidos" },
  { chave: "dismissed", rotulo: "Descartados" },
  { chave: "", rotulo: "Todos" },
] as const;

const TAMANHO = 25;

export function Alertas() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "sent";
  const pagina = Math.max(1, Number(params.get("pagina")) || 1);

  const consulta = {
    page: pagina,
    page_size: TAMANHO,
    ...(status ? { status: status as StatusDeAlerta } : {}),
  };

  const acoes = useTransicoes(consulta);

  const alertas = useQuery({
    queryKey: chaves.alertasCom(consulta),
    queryFn: () => listarAlertas(consulta),
    placeholderData: (anterior) => anterior,
  });

  function trocar(mudancas: { status?: string; pagina?: number }) {
    setParams(
      (atuais) => {
        const proximos = new URLSearchParams(atuais);
        if (mudancas.status !== undefined) {
          if (mudancas.status) proximos.set("status", mudancas.status);
          else proximos.set("status", "");
          // Trocar de aba reinicia a paginação: a aba nova tem outra contagem,
          // e manter `pagina=4` pediria uma página que pode não existir.
          proximos.delete("pagina");
        }
        if (mudancas.pagina !== undefined) {
          if (mudancas.pagina > 1) proximos.set("pagina", String(mudancas.pagina));
          else proximos.delete("pagina");
        }
        return proximos;
      },
      { replace: true },
    );
  }

  return (
    <>
      <h1>Alertas</h1>

      <div role="group" aria-label="Situação" className="filtro-status">
        {ABAS.map((aba) => (
          <button
            key={aba.chave}
            type="button"
            className={`filtro-chip${status === aba.chave ? " ativo" : ""}`}
            aria-pressed={status === aba.chave}
            onClick={() => trocar({ status: aba.chave })}
          >
            {aba.rotulo}
          </button>
        ))}
      </div>

      {alertas.isPending && <p className="sutil">Carregando alertas…</p>}

      {alertas.isError && (
        <p className="erro" role="alert">
          Não foi possível carregar os alertas.
        </p>
      )}

      {/* No nível da página, e não na linha: a linha desmonta durante a
          atualização otimista e levaria a mensagem embora. */}
      {acoes.falhou && (
        <p className="erro" role="alert">
          Não foi possível atualizar este alerta. Tente novamente.
        </p>
      )}

      {alertas.data && (
        <>
          {alertas.data.results.length === 0 ? (
            <p className="vazio">
              {status === "sent"
                ? "Nenhum alerta esperando por você."
                : "Nada aqui nesta situação."}
            </p>
          ) : (
            <ul className="lista-alertas">
              {alertas.data.results.map((alerta) => (
                <LinhaDeAlerta key={alerta.id} alerta={alerta} acoes={acoes} />
              ))}
            </ul>
          )}

          <Paginacao
            pagina={pagina}
            tamanho={TAMANHO}
            total={alertas.data.count}
            nesta={alertas.data.results.length}
            onPagina={(proxima) => trocar({ pagina: proxima })}
            // A API aceita `page_size`, mas a inbox não expõe o seletor: é uma
            // lista de leitura curta, não uma planilha para analisar.
            onTamanho={() => undefined}
          />
        </>
      )}
    </>
  );
}

/**
 * As transições vivem AQUI, na página, e não em cada linha.
 *
 * Não é preferência de organização — é correção. A atualização otimista remove
 * o alerta da lista, o que **desmonta** o componente da linha. Se a mutação
 * morasse ali dentro, o estado de erro dela morreria junto com o componente, e
 * uma falha do servidor produziria a pior combinação possível: o item
 * reaparece pelo rollback e nenhuma mensagem explica por quê. O usuário
 * concluiria que o clique não pegou e tentaria de novo.
 *
 * Descoberto por um teste que não conseguia encontrar a mensagem de erro.
 */
function useTransicoes(consulta: Record<string, unknown>) {
  const cliente = useQueryClient();
  const chave = chaves.alertasCom(consulta);

  function opcoes(executar: (id: string) => Promise<Alerta>) {
    return {
      mutationFn: executar,
      onMutate: async (id: string) => {
        // Sem o cancel, uma requisição em voo pode chegar DEPOIS da atualização
        // otimista e sobrescrevê-la com o estado antigo.
        await cliente.cancelQueries({ queryKey: chave });
        const anterior = cliente.getQueryData<Pagina<Alerta>>(chave);

        cliente.setQueryData<Pagina<Alerta>>(chave, (atual) =>
          atual
            ? {
                ...atual,
                // Sai da lista: a aba atual filtra por um status que este
                // alerta deixou de ter.
                results: atual.results.filter((item) => item.id !== id),
                count: Math.max(0, atual.count - 1),
              }
            : atual,
        );

        return { anterior };
      },
      onError: (
        _erro: unknown,
        _id: string,
        contexto?: { anterior?: Pagina<Alerta> },
      ) => {
        if (contexto?.anterior) cliente.setQueryData(chave, contexto.anterior);
      },
      onSettled: () => {
        // Invalida a árvore inteira de alertas, não só esta página: o contador
        // do cabeçalho e as outras abas também mudaram.
        //
        // Sem `await`, de propósito. O TanStack Query só despacha o estado
        // `error` da mutação DEPOIS que o `onSettled` resolve — aguardar aqui
        // faria a mensagem de falha esperar a revalidação inteira terminar.
        // Numa rede lenta o usuário veria o alerta reaparecer sem explicação e
        // só segundos depois entenderia o motivo.
        void cliente.invalidateQueries({ queryKey: chaves.alertas });
      },
    };
  }

  const lido = useMutation(opcoes(marcarComoLido));
  const descartado = useMutation(opcoes(descartar));

  return {
    marcarLido: (id: string) => lido.mutate(id),
    descartarAlerta: (id: string) => descartado.mutate(id),
    ocupado: lido.isPending || descartado.isPending,
    falhou: lido.isError || descartado.isError,
  };
}

function LinhaDeAlerta({
  alerta,
  acoes,
}: {
  alerta: Alerta;
  acoes: ReturnType<typeof useTransicoes>;
}) {
  return (
    <li className="linha-alerta">
      <div className="alerta-corpo">
        <Link to={`/tabelas/${alerta.table_id}`} className="nome-tabela">
          {alerta.label}
        </Link>
        <p className="sutil meta">
          {alerta.table_name} · vence em {formatarData(alerta.due_date ?? "")} · avisado
          em {formatarData(alerta.trigger_date)}
        </p>
        {alerta.is_stale && (
          // O vencimento mudou depois que o alerta foi gerado. Sem este aviso o
          // usuário agiria sobre uma data que não vale mais.
          <p className="aviso-inline">
            O vencimento foi alterado depois deste aviso — confira o registro.
          </p>
        )}
      </div>

      <div className="acoes">
        {alerta.status === "sent" && (
          <button
            type="button"
            className="secundario"
            disabled={acoes.ocupado}
            onClick={() => acoes.marcarLido(alerta.id)}
          >
            Marcar como lido
          </button>
        )}
        {alerta.status !== "dismissed" && (
          <button
            type="button"
            className="secundario"
            disabled={acoes.ocupado}
            onClick={() => acoes.descartarAlerta(alerta.id)}
          >
            Descartar
          </button>
        )}
      </div>
    </li>
  );
}
