/**
 * Armadilha 1 do plano: o access token nunca é persistido, então recarregar a
 * página começa sem sessão e só descobre se existe uma depois do
 * `POST /auth/refresh/`.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router";
import { describe, expect, it } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { RotaProtegida } from "../routes/RotaProtegida.tsx";
import { AuthProvider } from "./AuthProvider.tsx";

const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@remind.local",
  name: "Demo",
  timezone: "America/Sao_Paulo",
  created_at: "2026-08-20T12:00:00Z",
};

function montar(rotaInicial = "/") {
  return render(
    <MemoryRouter initialEntries={[rotaInicial]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<p>Tela de login</p>} />
          <Route element={<RotaProtegida />}>
            <Route path="/" element={<p>Conteúdo protegido</p>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function sessaoValida() {
  servidor.use(
    http.post(`${API}/auth/refresh/`, () => HttpResponse.json({ access: "tok" })),
    http.get(`${API}/auth/me/`, () => HttpResponse.json(USUARIO)),
  );
}

describe("AuthProvider", () => {
  it("reconstrói a sessão a partir do cookie e libera a rota protegida", async () => {
    sessaoValida();
    montar();

    expect(await screen.findByText("Conteúdo protegido")).toBeInTheDocument();
  });

  it("nunca mostra a tela de login enquanto o bootstrap está em voo", async () => {
    sessaoValida();
    montar();

    // O bug que este teste impede: tratar o instante inicial como "anônimo"
    // faz a RotaProtegida redirecionar antes da resposta do refresh chegar, e
    // o usuário logado vê a tela de login piscar a cada F5.
    expect(screen.queryByText("Tela de login")).not.toBeInTheDocument();
    expect(screen.getByText("Carregando…")).toBeInTheDocument();

    await screen.findByText("Conteúdo protegido");
    expect(screen.queryByText("Tela de login")).not.toBeInTheDocument();
  });

  it("manda para o login quando não há sessão", async () => {
    servidor.use(
      http.post(`${API}/auth/refresh/`, () =>
        HttpResponse.json({ detail: "Refresh token ausente." }, { status: 401 }),
      ),
    );
    montar();

    expect(await screen.findByText("Tela de login")).toBeInTheDocument();
  });

  it("trata refresh válido com /auth/me/ recusado como sessão encerrada", async () => {
    servidor.use(
      http.post(`${API}/auth/refresh/`, () => HttpResponse.json({ access: "tok" })),
      http.get(`${API}/auth/me/`, () =>
        HttpResponse.json({ detail: "inválido" }, { status: 403 }),
      ),
    );
    montar();

    // 403 e não 401 de propósito: o interceptor não entra em ação, então quem
    // precisa encerrar a sessão é o bootstrap. Sem isso o app ficaria preso em
    // "Carregando…" para sempre.
    expect(await screen.findByText("Tela de login")).toBeInTheDocument();
  });

  it("preserva o destino, com query string, em ?next=", async () => {
    servidor.use(
      http.post(`${API}/auth/refresh/`, () => HttpResponse.json({}, { status: 401 })),
    );

    // Lê o `next` de dentro do roteador. Inspecionar `window.location` não
    // serviria: o MemoryRouter guarda o histórico em memória e nunca toca na
    // URL do documento — o teste passaria com qualquer valor.
    function LoginEspiao() {
      const [params] = useSearchParams();
      return <p>next={params.get("next")}</p>;
    }

    render(
      <MemoryRouter initialEntries={["/tabelas/abc?page=2&status=overdue"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginEspiao />} />
            <Route element={<RotaProtegida />}>
              <Route path="/tabelas/:id" element={<p>protegido</p>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    // A query string precisa sobreviver: perder o `?status=overdue` devolveria
    // o usuário a uma tela diferente da que ele tentou abrir.
    await waitFor(() => {
      expect(
        screen.getByText("next=/tabelas/abc?page=2&status=overdue"),
      ).toBeInTheDocument();
    });
  });
});
