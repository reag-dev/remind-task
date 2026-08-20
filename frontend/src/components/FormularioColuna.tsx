import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client.ts";
import { atualizarColuna, criarColuna } from "../api/columns.ts";
import { chaves } from "../api/query.ts";
import {
  ROTULO_TIPO,
  TIPOS_DE_COLUNA,
  type Coluna,
  type TipoDeColuna,
} from "../api/tipos.ts";

type Props = {
  tabelaId: string;
  /** Ausente = criação. Presente = edição. */
  coluna?: Coluna;
  /** Já existe uma coluna de vencimento nesta tabela (RF06). */
  jaTemVencimento: boolean;
  onSair: () => void;
};

/** `options` só existe para `select`; qualquer outro tipo recusa a lista. */
function precisaDeOpcoes(tipo: TipoDeColuna): boolean {
  return tipo === "select";
}

export function FormularioColuna({
  tabelaId,
  coluna,
  jaTemVencimento,
  onSair,
}: Props) {
  const cliente = useQueryClient();
  const editando = coluna !== undefined;

  const [nome, setNome] = useState(coluna?.name ?? "");
  const [tipo, setTipo] = useState<TipoDeColuna>(coluna?.type ?? "text");
  const [obrigatoria, setObrigatoria] = useState(coluna?.is_required ?? false);
  const [sensivel, setSensivel] = useState(coluna?.is_sensitive ?? false);
  const [opcoes, setOpcoes] = useState((coluna?.options ?? []).join("\n"));

  const listaDeOpcoes = opcoes
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

  const salvar = useMutation({
    mutationFn: () => {
      const comuns = {
        name: nome.trim(),
        is_required: obrigatoria,
        is_sensitive: sensivel,
        // Enviar `[]` para tipo que não é `select` é o correto: o serializer
        // recusa lista NÃO-VAZIA em tipo errado, e mandar `undefined` deixaria
        // opções órfãs se a coluna já tivesse alguma.
        options: precisaDeOpcoes(tipo) ? listaDeOpcoes : [],
      };

      return editando
        ? atualizarColuna(tabelaId, coluna.id, comuns)
        : criarColuna(tabelaId, { ...comuns, type: tipo });
    },
    onSuccess: async () => {
      await Promise.all([
        cliente.invalidateQueries({ queryKey: chaves.colunas(tabelaId) }),
        // O detalhe da tabela carrega `columns[]` embutido; sem isto ele
        // continuaria mostrando a estrutura antiga.
        cliente.invalidateQueries({ queryKey: chaves.tabela(tabelaId) }),
      ]);
      onSair();
    },
  });

  const erro = salvar.error instanceof ApiError ? salvar.error : null;
  const vencimentoBloqueado = jaTemVencimento && coluna?.type !== "due_date";

  return (
    <form
      className="formulario cartao"
      noValidate
      onSubmit={(evento) => {
        evento.preventDefault();
        salvar.mutate();
      }}
    >
      <h2>{editando ? `Editar “${coluna.name}”` : "Nova coluna"}</h2>

      <label htmlFor="col-nome">Rótulo</label>
      <input
        id="col-nome"
        autoFocus
        value={nome}
        onChange={(evento) => setNome(evento.target.value)}
      />
      <Erros erro={erro} campo="name" />

      <label htmlFor="col-tipo">Tipo</label>
      <select
        id="col-tipo"
        value={tipo}
        disabled={editando}
        aria-describedby={editando ? "ajuda-tipo" : undefined}
        onChange={(evento) => setTipo(evento.target.value as TipoDeColuna)}
      >
        {TIPOS_DE_COLUNA.map((valor) => (
          <option
            key={valor}
            value={valor}
            // RF06: no máximo uma coluna de vencimento por tabela. O índice
            // parcial no banco garante; oferecer a opção para depois recusá-la
            // com 400 seria fazer o usuário descobrir a regra errando.
            disabled={valor === "due_date" && vencimentoBloqueado}
          >
            {ROTULO_TIPO[valor]}
            {valor === "due_date" && vencimentoBloqueado ? " — já existe uma" : ""}
          </option>
        ))}
      </select>
      {editando && (
        <p id="ajuda-tipo" className="sutil">
          O tipo não pode mudar: os registros já gravados foram validados contra ele.
          Para trocar, apague esta coluna e crie outra.
        </p>
      )}
      <Erros erro={erro} campo="type" />

      {precisaDeOpcoes(tipo) && (
        <>
          <label htmlFor="col-opcoes">Opções</label>
          <textarea
            id="col-opcoes"
            rows={4}
            value={opcoes}
            aria-describedby="ajuda-opcoes"
            onChange={(evento) => setOpcoes(evento.target.value)}
          />
          <p id="ajuda-opcoes" className="sutil">
            Uma por linha. Não pode haver repetidas.
          </p>
          <Erros erro={erro} campo="options" />
        </>
      )}

      <label className="caixa">
        <input
          type="checkbox"
          checked={obrigatoria}
          onChange={(evento) => setObrigatoria(evento.target.checked)}
        />
        Obrigatória
      </label>

      <label className="caixa">
        <input
          type="checkbox"
          checked={sensivel}
          onChange={(evento) => setSensivel(evento.target.checked)}
          aria-describedby="ajuda-sensivel"
        />
        Dado sensível
      </label>
      <p id="ajuda-sensivel" className="sutil">
        Fica mascarado na listagem e nunca aparece em alertas nem em logs (RS05).
      </p>
      <Erros erro={erro} campo="is_sensitive" />

      {erro && erro.status !== 400 && (
        <p className="erro" role="alert">
          Não foi possível salvar a coluna. Tente novamente.
        </p>
      )}
      {/* Erro sem campo associado — o serializer usa isso para a regra de
          vencimento duplicado quando ela escapa da validação da UI. */}
      <Erros erro={erro} campo="non_field_errors" />
      {erro?.status === 400 && erro.corpo.detail && (
        <p className="erro" role="alert">
          {erro.corpo.detail}
        </p>
      )}

      <div className="acoes-formulario">
        <button type="submit" disabled={salvar.isPending || !nome.trim()}>
          {salvar.isPending ? "Salvando…" : "Salvar"}
        </button>
        <button type="button" className="secundario" onClick={onSair}>
          Cancelar
        </button>
      </div>
    </form>
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
