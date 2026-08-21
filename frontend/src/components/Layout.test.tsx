import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { clienteDeTeste, digitador } from "../test/util.tsx";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider.tsx";
import { RotaProtegida } from "../routes/RotaProtegida.tsx";
import { API, servidor } from "../test/servidor.ts";
import { Layout } from "./Layout.tsx";

const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@remind.local",
  name: "Demo",
  timezone: "America/Sao_Paulo",
  created_at: "2026-08-20T12:00:00Z",
};

function montar() {
  // O `QueryClientProvider` e o handler de `/alerts/` entraram na Phase 6: o
  // Layout passou a montar o BadgeAlertas, que consulta a inbox. Sem os dois,
  // todo teste que renderiza a moldura quebra — foi assim que este quebrou.
  servidor.use(
    http.get(`${API}/alerts/`, () =>
      HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
    ),
  );

  return render(
    <QueryClientProvider client={clienteDeTeste()}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>tela de login</p>} />
            {/* Mesmo aninhamento do App: quem redireciona ao perder a sessão é
                a RotaProtegida, não o Layout. Montar o Layout solto testaria
                uma árvore que não existe em produção. */}
            <Route element={<RotaProtegida />}>
              <Route element={<Layout />}>
                <Route path="/" element={<p>miolo</p>} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Layout", () => {
  it("identifica a conta e renderiza o conteúdo da rota", async () => {
    servidor.use(
      http.post(`${API}/auth/refresh/`, () => HttpResponse.json({ access: "tok" })),
      http.get(`${API}/auth/me/`, () => HttpResponse.json(USUARIO)),
    );
    montar();

    expect(await screen.findByText("demo@remind.local")).toBeInTheDocument();
    expect(screen.getByText("miolo")).toBeInTheDocument();
  });

  it("chama o logout do backend ao sair, não só limpa o estado local", async () => {
    const deslogou = vi.fn();
    servidor.use(
      http.post(`${API}/auth/refresh/`, () => HttpResponse.json({ access: "tok" })),
      http.get(`${API}/auth/me/`, () => HttpResponse.json(USUARIO)),
      http.post(`${API}/auth/logout/`, () => {
        deslogou();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    montar();
    const usuario = digitador();

    await screen.findByText("demo@remind.local");
    await usuario.click(screen.getByRole("button", { name: "Sair" }));

    // Limpar só o token do lado do cliente deixaria o refresh válido por 7 dias
    // no cookie. O logout do backend o coloca na blacklist — é o que faz "sair"
    // significar alguma coisa (RS07).
    expect(deslogou).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("tela de login")).toBeInTheDocument();
  });
});
