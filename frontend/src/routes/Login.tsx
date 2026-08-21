import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { useAuth } from "../auth/contexto.ts";
import { mensagemDeLogin } from "../auth/mensagens.ts";

export function Login() {
  const { estado, entrar } = useAuth();
  const navegar = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  // `next` só é aceito se for um caminho interno. Sem esta checagem, um link
  // `/login?next=https://outro-site` viraria redirecionamento aberto depois de
  // autenticar — o atacante herdaria uma sessão recém-criada.
  const bruto = params.get("next") ?? "/";
  const destino = bruto.startsWith("/") && !bruto.startsWith("//") ? bruto : "/";

  if (estado.nome === "autenticado") return <Navigate to={destino} replace />;

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await entrar(email, senha);
      void navegar(destino, { replace: true });
    } catch (falha: unknown) {
      setErro(mensagemDeLogin(falha));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="formulario">
      <h1>Entrar</h1>
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

        <label htmlFor="senha">Senha</label>
        <input
          id="senha"
          type="password"
          autoComplete="current-password"
          required
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
        />

        {erro && (
          // `role="alert"` para que leitor de tela anuncie a falha; sem isso a
          // mensagem aparece só visualmente e quem navega por teclado continua
          // no campo de senha sem saber o que houve.
          <p className="erro" role="alert">
            {erro}
          </p>
        )}

        <button type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>

      <p>
        Não tem conta? <Link to="/registro">Criar conta</Link>
      </p>
    </main>
  );
}
