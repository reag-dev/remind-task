import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import { excluirRegistro, listarRegistros } from "../api/records.ts";
import { obterTabela } from "../api/tables.ts";
import type { Registro } from "../api/tipos.ts";
import { BotaoExportar } from "../components/BotaoExportar.tsx";
import { DialogoConfirmar } from "../components/DialogoConfirmar.tsx";
import { FormularioRegistro } from "../components/FormularioRegistro.tsx";
import { FiltroStatus } from "../components/FiltroStatus.tsx";
import { GridRegistros } from "../components/GridRegistros.tsx";
import { Paginacao } from "../components/Paginacao.tsx";
import { useTabelaServidor } from "../hooks/useTabelaServidor.ts";

type Edicao =
  { modo: "fechado" } | { modo: "novo" } | { modo: "editar"; registro: Registro };

export function TabelaRegistros() {
  const { id = "" } = useParams();
  const [edicao, setEdicao] = useState<Edicao>({ modo: "fechado" });
  const [aExcluir, setAExcluir] = useState<Registro | null>(null);

  const tabela = useQuery({
    queryKey: chaves.tabela(id),
    queryFn: () => obterTabela(id),
  });
  const { estado, consulta, filtrosDeExportacao, alterar, ordenarPor } =
    useTabelaServidor();

  const registros = useQuery({
    // A consulta entra na CHAVE: cada combinação de filtro, ordem e página é um
    // recurso próprio no cache. Sem isso, trocar de filtro sobrescreveria a
    // entrada anterior e voltar exigiria nova requisição.
    queryKey: chaves.registrosCom(id, consulta),
    queryFn: () => listarRegistros(id, consulta),
    // Mantém a tabela anterior na tela enquanto a próxima página chega, em vez
    // de piscar para o estado de carregamento a cada clique.
    placeholderData: (anterior) => anterior,
  });

  // Identidade estável: `montarColunas` entra num `useMemo` cujas dependências
  // incluem estes callbacks. Recriá-los a cada render invalidaria o memo e
  // remontaria o modelo de colunas em toda digitação da tela.
  const abrirEdicao = useCallback(
    (registro: Registro) => setEdicao({ modo: "editar", registro }),
    [],
  );
  const abrirExclusao = useCallback((registro: Registro) => setAExcluir(registro), []);

  if (tabela.isPending || registros.isPending) {
    return <p className="sutil">Carregando…</p>;
  }

  if (tabela.isError || registros.isError) {
    // Página fora do intervalo TAMBÉM responde 404 (ver
    // core/tests/test_pagination.py). Se a tabela carregou, o 404 veio da
    // listagem e significa "acabaram os registros", não "tabela não existe" —
    // tratar os dois igual jogaria o usuário para fora da tela por ter clicado
    // em "próxima" uma vez a mais, ou por ter apagado registros com um `?pagina=`
    // antigo na URL.
    const paginaVazia =
      !tabela.isError &&
      registros.error instanceof ApiError &&
      registros.error.status === 404 &&
      estado.pagina > 1;

    if (paginaVazia) {
      return (
        <p className="vazio" role="alert">
          Esta página não tem registros.{" "}
          <button
            type="button"
            className="ligacao"
            onClick={() => alterar({ pagina: 1 })}
          >
            Voltar para a primeira
          </button>
        </p>
      );
    }

    const erro = tabela.error ?? registros.error;
    // 404 vale tanto para tabela inexistente quanto para tabela de outro dono
    // (RS04). Falar em permissão aqui reintroduziria o vazamento que a API evita.
    const naoEncontrada = erro instanceof ApiError && erro.status === 404;

    return (
      <p className={naoEncontrada ? "vazio" : "erro"} role="alert">
        {naoEncontrada ? "Tabela não encontrada." : "Não foi possível carregar a tabela."}{" "}
        <Link to="/">Voltar para suas tabelas</Link>
      </p>
    );
  }

  const colunas = tabela.data.columns;
  const semColunas = colunas.length === 0;

  return (
    <>
      <div className="titulo-com-acao">
        <h1>{tabela.data.name}</h1>
        <div className="acoes">
          <Link to={`/tabelas/${id}/colunas`} className="botao secundario-link">
            Colunas ({colunas.length})
          </Link>
          <Link to={`/tabelas/${id}/alertas`} className="botao secundario-link">
            Alertas
          </Link>
          {edicao.modo === "fechado" && !semColunas && (
            <button
              type="button"
              className="botao"
              onClick={() => setEdicao({ modo: "novo" })}
            >
              Novo registro
            </button>
          )}
        </div>
      </div>

      {tabela.data.description && <p className="sutil">{tabela.data.description}</p>}

      {semColunas ? (
        <p className="vazio">
          Defina as colunas antes de inserir registros —{" "}
          <Link to={`/tabelas/${id}/colunas`}>configurar colunas</Link>.
        </p>
      ) : (
        <>
          {edicao.modo !== "fechado" && (
            <FormularioRegistro
              // Sem `key`, trocar de registro reaproveita a instância e o
              // rascunho do anterior permanece nos campos.
              key={edicao.modo === "editar" ? edicao.registro.id : "novo"}
              tabelaId={id}
              colunas={colunas}
              registro={edicao.modo === "editar" ? edicao.registro : undefined}
              onSair={() => setEdicao({ modo: "fechado" })}
            />
          )}

          <FiltroStatus
            selecionados={estado.status}
            ate={estado.vencendoAntesDe}
            de={estado.vencendoDepoisDe}
            onStatus={(status) => alterar({ status })}
            onIntervalo={(de, ate) =>
              alterar({ vencendoDepoisDe: de, vencendoAntesDe: ate })
            }
          />

          <GridRegistros
            colunas={colunas}
            registros={registros.data.results}
            comFiltro={
              estado.status.length > 0 ||
              estado.vencendoAntesDe !== null ||
              estado.vencendoDepoisDe !== null
            }
            ordenacao={estado.ordenacao}
            onOrdenar={ordenarPor}
            onEditar={abrirEdicao}
            onExcluir={abrirExclusao}
          />

          <div className="rodape-grid">
            <BotaoExportar
              tabelaId={id}
              filtros={filtrosDeExportacao}
              total={registros.data.count}
            />
          </div>

          <Paginacao
            pagina={estado.pagina}
            tamanho={estado.tamanho}
            total={registros.data.count}
            nesta={registros.data.results.length}
            onPagina={(pagina) => alterar({ pagina })}
            onTamanho={(tamanho) => alterar({ tamanho })}
          />
        </>
      )}

      {aExcluir && (
        <ConfirmarExclusaoDeRegistro
          tabelaId={id}
          registro={aExcluir}
          onFechar={() => setAExcluir(null)}
        />
      )}
    </>
  );
}

function ConfirmarExclusaoDeRegistro({
  tabelaId,
  registro,
  onFechar,
}: {
  tabelaId: string;
  registro: Registro;
  onFechar: () => void;
}) {
  const cliente = useQueryClient();
  const excluir = useMutation({
    mutationFn: () => excluirRegistro(tabelaId, registro.id),
    onSuccess: async () => {
      // Invalida por PREFIXO: alcanca todas as combinacoes de filtro/pagina em
      // cache, nao so a que esta na tela.
      await cliente.invalidateQueries({ queryKey: chaves.registros(tabelaId) });
      onFechar();
    },
  });

  return (
    <DialogoConfirmar
      titulo="Excluir registro"
      rotuloConfirmar="Excluir"
      confirmando={excluir.isPending}
      onConfirmar={() => excluir.mutate()}
      onCancelar={onFechar}
    >
      <p>Este registro será apagado. Não há como desfazer.</p>
      {excluir.isError && (
        <p className="erro" role="alert">
          Não foi possível excluir. Tente novamente.
        </p>
      )}
    </DialogoConfirmar>
  );
}
