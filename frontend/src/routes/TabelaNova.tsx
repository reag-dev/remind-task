import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import { criarTabela } from "../api/tables.ts";

/**
 * Padrão do backend para `alert_lead_days` (ver `tables.models.Table`).
 * Repetido aqui só como valor inicial do formulário — quem decide continua
 * sendo o backend quando o campo não é enviado.
 */
const ANTECEDENCIA_PADRAO = 3;

export function TabelaNova() {
  const cliente = useQueryClient();
  const navegar = useNavigate();
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [antecedencia, setAntecedencia] = useState(String(ANTECEDENCIA_PADRAO));

  const criar = useMutation({
    mutationFn: () =>
      criarTabela({
        name: nome.trim(),
        description: descricao.trim(),
        alert_lead_days: Number(antecedencia),
      }),
    onSuccess: async (tabela) => {
      await cliente.invalidateQueries({ queryKey: chaves.tabelas });
      // Direto para a tabela criada: o próximo passo obrigatório é definir
      // colunas, e uma tabela sem colunas não aceita registro nenhum.
      void navegar(`/tabelas/${tabela.id}`, { replace: true });
    },
  });

  const erro = criar.error instanceof ApiError ? criar.error : null;

  return (
    <div className="formulario">
      <h1>Nova tabela</h1>
      <form
        noValidate
        onSubmit={(evento) => {
          evento.preventDefault();
          criar.mutate();
        }}
      >
        <label htmlFor="nome">Nome</label>
        <input
          id="nome"
          required
          autoFocus
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
        />
        <Erros erro={erro} campo="name" />

        <label htmlFor="descricao">Descrição (opcional)</label>
        <textarea
          id="descricao"
          rows={3}
          value={descricao}
          onChange={(evento) => setDescricao(evento.target.value)}
        />
        <Erros erro={erro} campo="description" />

        <label htmlFor="antecedencia">
          Destacar como “próximo do vencimento” a partir de
        </label>
        <input
          id="antecedencia"
          type="number"
          min={0}
          max={365}
          value={antecedencia}
          onChange={(evento) => setAntecedencia(evento.target.value)}
          aria-describedby="ajuda-antecedencia"
        />
        {/* O campo controla o INDICADOR VISUAL (RF10), não o disparo de
            alerta — este vem das regras de antecedência da tabela, que são
            outra coisa. Sem esta linha os dois viram sinônimos na cabeça de
            quem usa. */}
        <p id="ajuda-antecedencia" className="sutil">
          Dias antes do vencimento. Não confunda com as regras de alerta, que decidem
          quando a notificação é gerada.
        </p>
        <Erros erro={erro} campo="alert_lead_days" />

        {erro && erro.status !== 400 && (
          <p className="erro" role="alert">
            Não foi possível criar a tabela. Tente novamente.
          </p>
        )}

        <button type="submit" disabled={criar.isPending || !nome.trim()}>
          {criar.isPending ? "Criando…" : "Criar tabela"}
        </button>
      </form>

      <p>
        <Link to="/">Voltar</Link>
      </p>
    </div>
  );
}

function Erros({ erro, campo }: { erro: ApiError | null; campo: string }) {
  const mensagens = erro?.status === 400 ? erro.campo(campo) : [];
  if (mensagens.length === 0) return null;

  return (
    <ul className="erro" role="alert">
      {mensagens.map((mensagem) => (
        <li key={mensagem}>{mensagem}</li>
      ))}
    </ul>
  );
}
