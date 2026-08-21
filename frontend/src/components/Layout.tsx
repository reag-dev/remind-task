import { Link, Outlet } from "react-router";

import { useAuth } from "../auth/contexto.ts";
import { BadgeAlertas } from "./BadgeAlertas.tsx";

/** Moldura das telas autenticadas: cabeçalho, identificação e saída. */
export function Layout() {
  const { estado, sair } = useAuth();

  return (
    <>
      <header className="cabecalho">
        <Link to="/" className="marca">
          remind-task
        </Link>
        <div className="cabecalho-direita">
          <BadgeAlertas />
          {estado.nome === "autenticado" && (
            <span className="sutil">{estado.usuario.email}</span>
          )}
          <button type="button" className="secundario" onClick={() => void sair()}>
            Sair
          </button>
        </div>
      </header>
      <main className="conteudo">
        <Outlet />
      </main>
    </>
  );
}
