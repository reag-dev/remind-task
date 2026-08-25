import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider.tsx";
import { API, servidor } from "../test/servidor.ts";
import { clienteDeTeste, digitador } from "../test/util.tsx";
import { Conta } from "./Conta.tsx";
import { RotaProtegida } from "./RotaProtegida.tsx";

const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@remind.local",
  name: "Demo",
  timezone: "America/Sao_Paulo",
  created_at: "2026-08-20T12:00:00Z",
};

function Onde() {
  const { pathname, search } = useLocation();
  return <p>rota: {pathname + search}</p>;
}

function montar() {
  servidor.use(
    http.post(`${API}/auth/refresh/`, () => HttpResponse.json({ access: "tok" })),
    http.get(`${API}/auth/me/`, () => HttpResponse.json(USUARIO)),
  );

  return render(
    <QueryClientProvider client={clienteDeTeste()}>
      <MemoryRouter initialEntries={["/conta"]}>
        <AuthProvider>
          <Routes>
            {/* Mesmo aninhamento do App: a tela só existe autenticada. */}
            <Route element={<RotaProtegida />}>
              <Route path="/conta" element={<Conta />} />
            </Route>
            <Route path="*" element={<Onde />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function abrirDialogo() {
  const usuario = digitador();
  await usuario.click(await screen.findByRole("button", { name: /excluir minha conta/i }));
  return usuario;
}

describe("Conta", () => {
  it("mostra os dados da conta", async () => {
    montar();

    expect(await screen.findByText("demo@remind.local")).toBeInTheDocument();
    expect(screen.getByText("America/Sao_Paulo")).toBeInTheDocument();
  });

  it("mantém a exclusão travada até o e-mail digitado bater", async () => {
    montar();
    const usuario = await abrirDialogo();

    const confirmar = screen.getByRole("button", { name: /^excluir conta$/i });
    expect(confirmar).toBeDisabled();

    // E-mail certo, senha ainda vazia: continua travado. As duas confirmações
    // protegem de coisas diferentes — o e-mail contra o clique errado, a senha
    // contra outra pessoa com o token na mão.
    await usuario.type(screen.getByLabelText("Seu e-mail"), USUARIO.email);
    expect(confirmar).toBeDisabled();

    await usuario.type(screen.getByLabelText("Senha"), "senha-de-teste-sem-valor");
    expect(confirmar).toBeEnabled();
  });

  it("não libera com o e-mail de outra conta", async () => {
    montar();
    const usuario = await abrirDialogo();

    await usuario.type(screen.getByLabelText("Seu e-mail"), "outro@remind.local");
    await usuario.type(screen.getByLabelText("Senha"), "senha-de-teste-sem-valor");

    expect(screen.getByRole("button", { name: /^excluir conta$/i })).toBeDisabled();
  });

  it("manda a senha no corpo do DELETE e sai para o login", async () => {
    let recebido: Record<string, unknown> | null = null;
    servidor.use(
      http.delete(`${API}/auth/me/`, async ({ request }) => {
        recebido = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(null, { status: 204 });
      }),
      http.post(`${API}/auth/logout/`, () => new HttpResponse(null, { status: 204 })),
    );
    montar();
    const usuario = await abrirDialogo();

    await usuario.type(screen.getByLabelText("Seu e-mail"), USUARIO.email);
    await usuario.type(screen.getByLabelText("Senha"), "senha-de-teste-sem-valor");
    await usuario.click(screen.getByRole("button", { name: /^excluir conta$/i }));

    expect(await screen.findByText("rota: /login?conta-excluida=1")).toBeInTheDocument();
    expect(recebido).toEqual({ password: "senha-de-teste-sem-valor" });
  });

  it("mostra a mensagem do backend quando a senha está errada", async () => {
    servidor.use(
      http.delete(`${API}/auth/me/`, () =>
        HttpResponse.json({ password: ["Senha incorreta."] }, { status: 400 }),
      ),
    );
    montar();
    const usuario = await abrirDialogo();

    await usuario.type(screen.getByLabelText("Seu e-mail"), USUARIO.email);
    await usuario.type(screen.getByLabelText("Senha"), "nao-e-a-senha");
    await usuario.click(screen.getByRole("button", { name: /^excluir conta$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Senha incorreta.");
    // Continua na tela, com o diálogo aberto: a conta não foi apagada.
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
  });

  it("não chama a API ao cancelar", async () => {
    const chamou = vi.fn();
    servidor.use(
      http.delete(`${API}/auth/me/`, () => {
        chamou();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    montar();
    const usuario = await abrirDialogo();

    await usuario.click(screen.getByRole("button", { name: /cancelar/i }));

    expect(chamou).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Seu e-mail")).not.toBeInTheDocument();
  });
});
