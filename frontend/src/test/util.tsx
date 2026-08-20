import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

/**
 * Cliente de query para teste.
 *
 * `retry: false` mesmo tendo a política real em `criarQueryClient`: aqui o que
 * se testa é a tela, e uma query que repete transforma cada caso de erro em
 * segundos de espera. A política de retry em si é responsabilidade de
 * `api/query.test.ts`.
 *
 * Um cliente NOVO por teste, nunca compartilhado: o cache é estado global, e um
 * teste que carrega a lista deixaria o seguinte começar com dados prontos.
 */
export function clienteDeTeste(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

type Opcoes = {
  rota?: string;
  /** Caminho da rota que renderiza `elemento`. Padrão: o próprio `rota`. */
  caminho?: string;
};

/**
 * Sonda de navegação.
 *
 * Imprime o caminho ATUAL, lido do roteador. Uma versão que imprimisse a rota
 * inicial provaria apenas "saiu da tela", não "chegou onde devia" — e um
 * `navigate()` para o destino errado passaria no teste.
 */
function Destino() {
  const local = useLocation();
  return <p>{`rota: ${local.pathname}${local.search}`}</p>;
}

export function renderizar(
  elemento: React.ReactNode,
  { rota = "/", caminho }: Opcoes = {},
): RenderResult {
  return render(
    <QueryClientProvider client={clienteDeTeste()}>
      <MemoryRouter initialEntries={[rota]}>
        <Routes>
          <Route path={caminho ?? rota} element={elemento} />
          <Route path="*" element={<Destino />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
