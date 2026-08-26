import { useState } from "react";

import { excluirConta } from "../api/auth.ts";
import { ApiError } from "../api/client.ts";
import { useAuth } from "../auth/contexto.ts";
import { DialogoConfirmar } from "../components/DialogoConfirmar.tsx";

export function Conta() {
  const { estado, sair } = useAuth();
  const [aberto, setAberto] = useState(false);
  const [emailDigitado, setEmailDigitado] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState(false);

  if (estado.nome !== "autenticado") return null;

  const email = estado.usuario.email;

  // DUAS confirmações, e elas não são redundantes — protegem de coisas
  // diferentes.
  //
  // Digitar o e-mail é contra o clique no lugar errado: é o atrito que
  // transforma "confirmar" em um ato deliberado, e o motivo de não ser um
  // "tem certeza?" com dois botões lado a lado.
  //
  // A senha é contra outra pessoa: um access token roubado já dá acesso de
  // leitura e escrita — ruim, mas recuperável. Apagar a conta não é. Quem
  // confere a senha é o backend; aqui ela é só o campo.
  const confere = emailDigitado.trim().toLowerCase() === email.toLowerCase();
  const podeExcluir = confere && senha.length > 0;

  function fechar() {
    setAberto(false);
    setEmailDigitado("");
    setSenha("");
    setErro(null);
  }

  async function excluir() {
    // Cinto além do suspensório: o botão já vem desabilitado enquanto a
    // confirmação não bate. Um `onConfirmar` que confia só no `disabled` do DOM
    // é o tipo de coisa que um teclado, um leitor de tela ou um refactor do
    // diálogo contornam sem querer.
    if (!podeExcluir) return;

    setErro(null);
    setExcluindo(true);
    try {
      await excluirConta(senha);
    } catch (falha: unknown) {
      if (falha instanceof ApiError && falha.status === 400) {
        setErro(falha.campo("password")[0] ?? "Não foi possível excluir a conta.");
      } else {
        setErro("Não foi possível falar com o servidor. Verifique sua conexão.");
      }
      setExcluindo(false);
      return;
    }

    // Daqui para baixo a conta NÃO existe mais, e nada aqui pode ser tratado
    // como falha da exclusão — por isso fora do `try` acima.
    //
    // `sair()` mesmo com a conta já apagada: o que ele faz de útil aqui é
    // limpar o estado local (token em memória, cache de queries). O logout no
    // servidor é idempotente e não se importa com um refresh já invalidado.
    //
    // E esta tela NÃO navega. Quem leva ao `/login?conta-excluida=1` é a
    // `<RotaProtegida>`, a partir do motivo — um `navegar()` daqui perde a
    // corrida contra o guard, que renderiza assim que o estado vira "anônimo",
    // ainda em `/conta`, e cujo `<Navigate>` roda depois, já no efeito.
    await sair("conta-excluida");
  }

  return (
    <section className="conta">
      <h1>Conta</h1>

      <dl className="dados-da-conta">
        <dt>E-mail</dt>
        <dd>{email}</dd>
        <dt>Nome</dt>
        <dd>{estado.usuario.name || "—"}</dd>
        <dt>Fuso horário</dt>
        <dd>{estado.usuario.timezone}</dd>
      </dl>

      <section className="zona-de-perigo">
        <h2>Excluir conta</h2>
        <p>
          Apaga a conta e <strong>tudo</strong> que está nela: tabelas,
          registros, regras de alerta e alertas. Não há como desfazer, e não há
          período de carência.
        </p>
        <button type="button" className="destrutivo" onClick={() => setAberto(true)}>
          Excluir minha conta
        </button>
      </section>

      {aberto && (
        <DialogoConfirmar
          titulo="Excluir conta definitivamente"
          rotuloConfirmar="Excluir conta"
          confirmando={excluindo}
          confirmarDesabilitado={!podeExcluir}
          onConfirmar={() => void excluir()}
          onCancelar={fechar}
        >
          <p>
            Para confirmar, digite <strong>{email}</strong> e a senha da conta.
          </p>

          <label htmlFor="confirmacao-email">Seu e-mail</label>
          <input
            id="confirmacao-email"
            autoComplete="off"
            value={emailDigitado}
            onChange={(e) => setEmailDigitado(e.target.value)}
          />

          <label htmlFor="confirmacao-senha">Senha</label>
          <input
            id="confirmacao-senha"
            type="password"
            autoComplete="current-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />

          {erro && (
            <p className="erro" role="alert">
              {erro}
            </p>
          )}

          {/* Um botão desabilitado sem explicação é um beco: a pessoa não sabe
              se falta algo ou se a tela quebrou. A trava está no botão
              (`confirmarDesabilitado`), e a razão dela está aqui. */}
          {!podeExcluir && (
            <p className="sutil" role="status">
              Digite o e-mail exatamente como está acima e a senha para liberar a
              exclusão.
            </p>
          )}
        </DialogoConfirmar>
      )}
    </section>
  );
}
