import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthProvider.tsx";
import { API, servidor } from "../test/servidor.ts";
import { Login } from "./Login.tsx";

const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@remind.local",
  name: "Demo",
  timezone: "America/Sao_Paulo",
  created_at: "2026-08-20T12:00:00Z",
};

function Destino() {
  const local = useLocation();
  return <p>chegou em {local.pathname}</p>;
}

function montar(rota = "/login") {
  // Sem sessão prévia: o bootstrap precisa resolver para "anônimo" antes de a
  // tela de login ficar utilizável.
  servidor.use(
    http.post(`${API}/auth/refresh/`, () => HttpResponse.json({}, { status: 401 })),
  );

  return render(
    <MemoryRouter initialEntries={[rota]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Destino />} />
          <Route path="/tabelas" element={<Destino />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function preencherEEnviar() {
  const usuario = userEvent.setup();
  await usuario.type(screen.getByLabelText("E-mail"), "demo@remind.local");
  await usuario.type(screen.getByLabelText("Senha"), "seja-la-o-que-for");
  await usuario.click(screen.getByRole("button", { name: /entrar/i }));
}

describe("Login", () => {
  it("traduz o 429 do django-axes em uma mensagem com o tempo de espera", async () => {
    // O AxesMiddleware responde ANTES do DRF: corpo em texto puro, em inglês.
    // Verificado contra a API real em 2026-08-20.
    servidor.use(
      http.post(`${API}/auth/login/`, () =>
        HttpResponse.text("Account locked: too many login attempts.", { status: 429 }),
      ),
    );
    montar();
    await preencherEEnviar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Muitas tentativas de login");
    expect(alerta).toHaveTextContent("15 minutos");
    // O texto do backend não pode vazar para a tela: está em inglês e não diz
    // ao usuário quanto tempo esperar.
    expect(alerta).not.toHaveTextContent("Account locked");
  });

  it("não distingue e-mail inexistente de senha errada", async () => {
    servidor.use(
      http.post(`${API}/auth/login/`, () =>
        HttpResponse.json(
          { detail: "No active account found with the given credentials" },
          { status: 401 },
        ),
      ),
    );
    montar();
    await preencherEEnviar();

    // Enumeração de contas: uma mensagem que diferencie os dois casos deixa
    // qualquer um descobrir quais e-mails têm conta.
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "E-mail ou senha inválidos.",
    );
  });

  it("leva ao destino interno pedido em ?next=", async () => {
    servidor.use(
      http.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ access: "tok", user: USUARIO }),
      ),
    );
    montar("/login?next=%2Ftabelas");
    await preencherEEnviar();

    expect(await screen.findByText("chegou em /tabelas")).toBeInTheDocument();
  });

  it.each([
    ["https://exemplo-malicioso.test/colher", "URL absoluta"],
    ["//exemplo-malicioso.test/colher", "URL sem esquema"],
  ])("descarta %s em ?next= (%s)", async (destino) => {
    servidor.use(
      http.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ access: "tok", user: USUARIO }),
      ),
    );
    montar(`/login?next=${encodeURIComponent(destino)}`);
    await preencherEEnviar();

    // Redirecionamento aberto: sem a checagem, o atacante manda a vítima para o
    // seu próprio site logo após ela autenticar — com a sessão recém-criada.
    // `//host` é o caso que passa despercebido, porque começa com "/".
    expect(await screen.findByText("chegou em /")).toBeInTheDocument();
  });
});
