import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "../auth/contexto.ts";

export function RotaProtegida() {
  const { estado } = useAuth();
  const local = useLocation();

  // O estado "carregando" existe para este `if`. Sem ele, o bootstrap de sessão
  // ainda em voo seria lido como "anônimo" e todo F5 numa página interna jogaria
  // o usuário para o login.
  if (estado.nome === "carregando") {
    return <p className="carregando">Carregando…</p>;
  }

  if (estado.nome === "anonimo") {
    const destino = `${local.pathname}${local.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(destino)}`} replace />;
  }

  return <Outlet />;
}
