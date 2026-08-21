import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { cadastrar } from "../api/auth.ts";
import { ApiError } from "../api/client.ts";
import { useAuth } from "../auth/contexto.ts";

/** Fuso do browser, que é o padrão certo para `users.timezone`. */
const FUSO = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function Registro() {
  const { estado, entrar } = useAuth();
  const navegar = useNavigate();
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [erros, setErros] = useState<ApiError | null>(null);
  const [geral, setGeral] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (estado.nome === "autenticado") return <Navigate to="/" replace />;

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    setErros(null);
    setGeral(null);
    setEnviando(true);
    try {
      await cadastrar({ email, name: nome, password: senha, timezone: FUSO });
      // Cadastro não devolve token — a API separa criar conta de abrir sessão.
      // Entrar em seguida evita obrigar o usuário a digitar tudo de novo.
      await entrar(email, senha);
      void navegar("/", { replace: true });
    } catch (falha: unknown) {
      if (falha instanceof ApiError && falha.status === 400) {
        // O RegisterSerializer devolve os erros já mapeados por campo — inclusive
        // os dos AUTH_PASSWORD_VALIDATORS em `password`, e não em
        // `non_field_errors`. Ver o comentário do `validate()` dele.
        setErros(falha);
      } else {
        setGeral("Não foi possível criar a conta. Tente novamente.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="formulario">
      <h1>Criar conta</h1>
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
        <ErrosDoCampo erros={erros} campo="email" />

        <label htmlFor="nome">Nome</label>
        <input
          id="nome"
          autoComplete="name"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
        />
        <ErrosDoCampo erros={erros} campo="name" />

        <label htmlFor="senha">Senha</label>
        <input
          id="senha"
          type="password"
          autoComplete="new-password"
          required
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
        />
        <ErrosDoCampo erros={erros} campo="password" />

        {geral && (
          <p className="erro" role="alert">
            {geral}
          </p>
        )}

        <button type="submit" disabled={enviando}>
          {enviando ? "Criando…" : "Criar conta"}
        </button>
      </form>

      <p>
        Já tem conta? <Link to="/login">Entrar</Link>
      </p>
    </main>
  );
}

function ErrosDoCampo({ erros, campo }: { erros: ApiError | null; campo: string }) {
  const mensagens = erros?.campo(campo) ?? [];
  if (mensagens.length === 0) return null;

  return (
    <ul className="erro" role="alert">
      {mensagens.map((mensagem) => (
        <li key={mensagem}>{mensagem}</li>
      ))}
    </ul>
  );
}
