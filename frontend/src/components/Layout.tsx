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
            // O e-mail vira o link para a conta: é onde o usuário procura por
            // "meus dados" antes de procurar um menu, e evita mais um item no
            // cabeçalho para uma tela que se visita duas vezes por ano.
            <Link to="/conta" className="sutil">
              {estado.usuario.email}
            </Link>
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
