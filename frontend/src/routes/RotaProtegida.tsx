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
    // O `next` pressupõe que existe para onde voltar depois de entrar, e quem
    // acabou de apagar a própria conta não tem: a rota que ele estava vendo
    // morreu junto com os dados. Mandar de volta para `/conta` seria prometer
    // uma volta que não acontece — e é aqui que o destino é decidido porque é
    // aqui que se sabe que a sessão acabou, antes de qualquer tela reagir.
    if (estado.motivo === "conta-excluida") {
      return <Navigate to="/login?conta-excluida=1" replace />;
    }

    const destino = `${local.pathname}${local.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(destino)}`} replace />;
  }

  return <Outlet />;
}
