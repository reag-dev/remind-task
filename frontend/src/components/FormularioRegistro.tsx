import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client.ts";
import { chaves } from "../api/query.ts";
import { atualizarRegistro, criarRegistro } from "../api/records.ts";
import type { Coluna, DadosDoRegistro, Registro } from "../api/tipos.ts";
import { paraTexto } from "../formato.ts";

type Props = {
  tabelaId: string;
  colunas: Coluna[];
  /** Ausente = inserção (RF07). Presente = edição (RF08). */
  registro?: Registro;
  onSair: () => void;
};

/**
 * Valores do formulário como texto.
 *
 * Todo input do HTML devolve string; a conversão para o tipo real acontece uma
 * vez só, em `paraJson`, no envio. Guardar o valor já convertido obrigaria a
 * converter de volta a cada tecla e perderia estados intermediários — digitar
 * "1," num campo numérico viraria `NaN` e apagaria o que o usuário escreveu.
 */
type Rascunho = Record<string, string | boolean>;

function rascunhoInicial(colunas: Coluna[], registro?: Registro): Rascunho {
  const inicial: Rascunho = {};
  for (const coluna of colunas) {
    const valor = registro?.data?.[coluna.key];
    inicial[coluna.key] =
      coluna.type === "boolean"
        ? valor === true
        : valor === null || valor === undefined
          ? ""
          : paraTexto(valor);
  }
  return inicial;
}

function paraJson(colunas: Coluna[], rascunho: Rascunho): DadosDoRegistro {
  const dados: DadosDoRegistro = {};

  for (const coluna of colunas) {
    const bruto = rascunho[coluna.key];

    if (coluna.type === "boolean") {
      dados[coluna.key] = bruto === true;
      continue;
    }

    const texto = typeof bruto === "string" ? bruto.trim() : "";
    if (texto === "") {
      // `null` explícito, não a chave ausente. O validador do backend mescla o
      // delta sobre o valor atual numa edição — omitir a chave manteria o valor
      // antigo, e apagar um campo ficaria impossível pela interface.
      dados[coluna.key] = null;
      continue;
    }

    if (coluna.type === "number") {
      const numero = Number(texto.replace(",", "."));
      // Texto que não é número vai cru para o backend responder 400 com a
      // mensagem dele. Converter para NaN aqui produziria `null` no JSON e o
      // erro sumiria — o campo pareceria ter sido apagado de propósito.
      dados[coluna.key] = Number.isNaN(numero) ? texto : numero;
      continue;
    }

    dados[coluna.key] = texto;
  }

  return dados;
}

export function FormularioRegistro({ tabelaId, colunas, registro, onSair }: Props) {
  const cliente = useQueryClient();
  const editando = registro !== undefined;
  const [rascunho, setRascunho] = useState<Rascunho>(() =>
    rascunhoInicial(colunas, registro),
  );

  const salvar = useMutation({
    mutationFn: () => {
      const dados = paraJson(colunas, rascunho);
      return editando
        ? atualizarRegistro(tabelaId, registro.id, dados)
        : criarRegistro(tabelaId, dados);
    },
    onSuccess: async () => {
      await cliente.invalidateQueries({ queryKey: chaves.registros(tabelaId) });
      onSair();
    },
  });

  const erro = salvar.error instanceof ApiError ? salvar.error : null;

  /**
   * Erros por coluna.
   *
   * O `validate_data` do serializer devolve `{"data": {"cpf": ["..."]}}` —
   * aninhado sob `data`, não no nível de cima. Procurar `erro.campo("cpf")`
   * direto não acharia nada e o usuário veria o formulário recusado sem
   * nenhuma explicação.
   */
  const bruto = erro?.status === 400 ? erro.corpo.data : undefined;
  const errosPorColuna =
    // `!Array.isArray` não é detalhe: em JavaScript um array TAMBÉM é `object`,
    // e o DRF usa as duas formas no mesmo campo — `{"data": {"cpf": [...]}}`
    // para erro de coluna, `{"data": ["Chave desconhecida: x."]}` para erro do
    // campo inteiro. Sem esta distinção o segundo caso entra no caminho de
    // erros-por-coluna, não casa com chave nenhuma e a mensagem some da tela:
    // o formulário é recusado sem dizer por quê.
    typeof bruto === "object" && bruto !== null && !Array.isArray(bruto) ? bruto : {};

  function definir(chave: string, valor: string | boolean) {
    setRascunho((atual) => ({ ...atual, [chave]: valor }));
  }

  return (
    <form
      className="formulario cartao"
      noValidate
      onSubmit={(evento) => {
        evento.preventDefault();
        salvar.mutate();
      }}
    >
      <h2>{editando ? "Editar registro" : "Novo registro"}</h2>

      {colunas.map((coluna) => (
        <CampoDaColuna
          key={coluna.id}
          coluna={coluna}
          valor={rascunho[coluna.key] ?? ""}
          erros={errosPorColuna[coluna.key]}
          onMudar={(valor) => definir(coluna.key, valor)}
        />
      ))}

      {erro?.status === 400 && Object.keys(errosPorColuna).length === 0 && (
        <p className="erro" role="alert">
          {erro.campo("data")[0] ?? erro.corpo.detail ?? "Dados inválidos."}
        </p>
      )}
      {erro && erro.status !== 400 && (
        <p className="erro" role="alert">
          Não foi possível salvar o registro. Tente novamente.
        </p>
      )}

      <div className="acoes-formulario">
        <button type="submit" disabled={salvar.isPending}>
          {salvar.isPending ? "Salvando…" : "Salvar"}
        </button>
        <button type="button" className="secundario" onClick={onSair}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

function CampoDaColuna({
  coluna,
  valor,
  erros,
  onMudar,
}: {
  coluna: Coluna;
  valor: string | boolean;
  erros: string[] | string | undefined;
  onMudar: (valor: string | boolean) => void;
}) {
  const id = `campo-${coluna.key}`;
  const lista = erros === undefined ? [] : Array.isArray(erros) ? erros : [erros];
  const texto = typeof valor === "string" ? valor : "";

  return (
    <>
      <label htmlFor={id}>
        {coluna.name}
        {coluna.is_required && (
          <>
            {" "}
            <span aria-hidden="true">*</span>
            <span className="oculto-visual">(obrigatório)</span>
          </>
        )}
      </label>

      {coluna.type === "boolean" ? (
        <input
          id={id}
          type="checkbox"
          checked={valor === true}
          onChange={(evento) => onMudar(evento.target.checked)}
        />
      ) : coluna.type === "select" ? (
        <select id={id} value={texto} onChange={(evento) => onMudar(evento.target.value)}>
          {/* Opção vazia sempre presente: sem ela o primeiro item da lista
              viraria o valor de fato, e uma coluna opcional ficaria impossível
              de deixar em branco. */}
          <option value="">—</option>
          {(coluna.options ?? []).map((opcao) => (
            <option key={opcao} value={opcao}>
              {opcao}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={tipoDeInput(coluna.type)}
          value={texto}
          // `is_sensitive` não vira `type="password"`: quem digita precisa
          // conferir o que digitou, e a proteção do RS05 é sobre exibição em
          // lista, log e alerta — não sobre o próprio dono ver o próprio dado.
          onChange={(evento) => onMudar(evento.target.value)}
        />
      )}

      {lista.length > 0 && (
        <ul className="erro" role="alert">
          {lista.map((mensagem) => (
            <li key={mensagem}>{mensagem}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function tipoDeInput(tipo: Coluna["type"]): string {
  switch (tipo) {
    case "number":
      return "number";
    case "date":
    case "due_date":
      return "date";
    case "datetime":
      return "datetime-local";
    case "email":
      return "email";
    default:
      return "text";
  }
}
