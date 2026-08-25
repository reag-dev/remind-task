import { useState } from "react";
import { Link } from "react-router";

import { pedirRecuperacao } from "../api/auth.ts";
import { ApiError } from "../api/client.ts";

export function EsqueciSenha() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await pedirRecuperacao(email);
      setEnviado(true);
    } catch (falha: unknown) {
      // 429 é o teto por IP (`password_reset`), e precisa de mensagem própria:
      // "tente de novo" sem dizer que existe um limite faria o usuário repetir
      // e continuar batendo na parede.
      if (falha instanceof ApiError && falha.status === 429) {
        setErro("Muitos pedidos deste endereço. Tente novamente mais tarde.");
      } else if (falha instanceof ApiError && falha.status === 400) {
        setErro("Informe um e-mail válido.");
      } else {
        setErro("Não foi possível falar com o servidor. Verifique sua conexão.");
      }
    } finally {
      setEnviando(false);
    }
  }

  // A MESMA tela para conta existente e inexistente.
  //
  // A API responde 204 nos dois casos de propósito, e escrever aqui "enviamos
  // para o seu e-mail" contra "não encontramos esse e-mail" recriaria no
  // cliente exatamente o oráculo de cadastro que o servidor recusa ser. A
  // redação abaixo é condicional na FORMA — "se houver uma conta" —, que é o
  // que permite ser honesta sem confirmar nada.
  if (enviado) {
    return (
      <main className="formulario">
        <h1>Verifique seu e-mail</h1>
        <p role="status">
          Se houver uma conta com <strong>{email}</strong>, enviamos um link para
          redefinir a senha. Ele vale por uma hora e só pode ser usado uma vez.
        </p>
        <p>
          Não chegou? Confira a caixa de spam ou <Link to="/login">volte ao login</Link>.
        </p>
      </main>
    );
  }

  return (
    <main className="formulario">
      <h1>Esqueci minha senha</h1>
      <p>
        Informe o e-mail da conta. Se houver cadastro, você recebe um link para
        escolher uma senha nova.
      </p>
      <form onSubmit={(e) => void enviar(e)} noValidate>
        <label htmlFor="email">E-mail</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        {erro && (
          <p className="erro" role="alert">
            {erro}
          </p>
        )}

        <button type="submit" disabled={enviando}>
          {enviando ? "Enviando…" : "Enviar link"}
        </button>
      </form>

      <p>
        Lembrou a senha? <Link to="/login">Entrar</Link>
      </p>
    </main>
  );
}
