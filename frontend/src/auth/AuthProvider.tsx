import { useCallback, useEffect, useMemo, useState } from "react";

import * as api from "../api/auth.ts";
import { registrarRenovacao } from "../api/client.ts";
import { ContextoDeAuth, type EstadoDeAuth, type MotivoDeSaida } from "./contexto.ts";
import { renovarAccessToken } from "./refresh.ts";
import { gravarAccessToken } from "./sessao.ts";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [estado, setEstado] = useState<EstadoDeAuth>({ nome: "carregando" });

  // Sem motivo por padrão: o caminho comum (token morto, logout no menu) não
  // tem nada a explicar, e é a `<RotaProtegida>` que lê o motivo quando existe.
  const encerrarLocalmente = useCallback((motivo?: MotivoDeSaida) => {
    gravarAccessToken(null);
    setEstado({ nome: "anonimo", motivo });
  }, []);

  // Bootstrap: reconstrói a sessão a partir do cookie httpOnly.
  //
  // Roda uma vez. Em <StrictMode> o efeito é invocado duas vezes no dev, e o
  // single-flight de `renovarAccessToken` faz a segunda invocação compartilhar a
  // promessa da primeira em vez de queimar o refresh recém-rotacionado — o
  // mesmo mecanismo que protege as requisições paralelas protege isto aqui.
  useEffect(() => {
    let cancelado = false;

    void (async () => {
      const token = await renovarAccessToken();
      if (cancelado) return;

      if (!token) {
        encerrarLocalmente();
        return;
      }

      // Ordem obrigatória: gravar o token ANTES de chamar /auth/me/, que é uma
      // rota protegida e leria `null` no header se a ordem se invertesse.
      gravarAccessToken(token);
      try {
        const usuario = await api.eu();
        if (!cancelado) setEstado({ nome: "autenticado", usuario });
      } catch {
        if (!cancelado) encerrarLocalmente();
      }
    })();

    return () => {
      cancelado = true;
    };
  }, [encerrarLocalmente]);

  // Interceptor de 401 do cliente HTTP. Devolve `true` quando renovou, e é isso
  // que autoriza `request` a repetir a chamada original uma única vez.
  useEffect(() => {
    registrarRenovacao(async () => {
      const token = await renovarAccessToken();
      if (!token) {
        encerrarLocalmente();
        return false;
      }
      gravarAccessToken(token);
      return true;
    });
  }, [encerrarLocalmente]);

  const entrar = useCallback(async (email: string, senha: string) => {
    const { access, user } = await api.login({ email, password: senha });
    gravarAccessToken(access);
    setEstado({ nome: "autenticado", usuario: user });
  }, []);

  const sair = useCallback(
    async (motivo?: MotivoDeSaida) => {
      await api.logout();
      encerrarLocalmente(motivo);
    },
    [encerrarLocalmente],
  );

  const valor = useMemo(() => ({ estado, entrar, sair }), [estado, entrar, sair]);

  return <ContextoDeAuth value={valor}>{children}</ContextoDeAuth>;
}
