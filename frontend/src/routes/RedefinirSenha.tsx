import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { redefinirSenha } from "../api/auth.ts";
import { ApiError } from "../api/client.ts";

export function RedefinirSenha() {
  const [params] = useSearchParams();
  const navegar = useNavigate();
  const [senha, setSenha] = useState("");
  const [erros, setErros] = useState<string[]>([]);
  const [linkMorto, setLinkMorto] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";

  // Sem uid/token não há o que enviar. Vale a checagem antes do formulário
  // porque o caminho mais comum de chegar aqui sem eles é um cliente de e-mail
  // que quebrou a URL em duas linhas — e mandar o usuário preencher uma senha
  // para só então dizer "link inválido" seria cruel sem motivo.
  if (!uid || !token) {
    return <LinkInvalido motivo="O link está incompleto." />;
  }

  if (linkMorto) {
    return <LinkInvalido motivo="Este link expirou ou já foi usado." />;
  }

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    setErros([]);
    setEnviando(true);
    try {
      await redefinirSenha({ uid, token, password: senha });
      // `replace` para o botão "voltar" não trazer o usuário de volta a um
      // formulário cujo token já foi queimado.
      void navegar("/login?redefinida=1", { replace: true });
    } catch (falha: unknown) {
      if (falha instanceof ApiError && falha.status === 400) {
        const doToken = falha.campo("token");
        // O backend não distingue "uid desconhecido" de "token errado" — os dois
        // chegam como erro em `token`, e a tela também não deve distinguir.
        if (doToken.length > 0) setLinkMorto(true);
        else setErros(falha.campo("password"));
      } else if (falha instanceof ApiError && falha.status === 429) {
        setErros(["Muitas tentativas. Aguarde antes de tentar de novo."]);
      } else {
        setErros(["Não foi possível falar com o servidor. Verifique sua conexão."]);
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="formulario">
      <h1>Escolher nova senha</h1>
      <form onSubmit={(e) => void enviar(e)} noValidate>
        <label htmlFor="senha">Nova senha</label>
        <input
          id="senha"
          type="password"
          autoComplete="new-password"
          required
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
        />

        {erros.length > 0 && (
          <ul className="erro" role="alert">
            {erros.map((mensagem) => (
              <li key={mensagem}>{mensagem}</li>
            ))}
          </ul>
        )}

        <button type="submit" disabled={enviando}>
          {enviando ? "Salvando…" : "Salvar senha"}
        </button>
      </form>

      <p>
        Ao salvar, todas as sessões abertas nesta conta são encerradas — inclusive
        em outros dispositivos.
      </p>
    </main>
  );
}

function LinkInvalido({ motivo }: { motivo: string }) {
  return (
    <main className="formulario">
      <h1>Link inválido</h1>
      <p role="alert">{motivo} Peça um novo para continuar.</p>
      <p>
        <Link to="/esqueci-senha">Pedir novo link</Link> · <Link to="/login">Entrar</Link>
      </p>
    </main>
  );
}
