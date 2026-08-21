import { render, screen } from "@testing-library/react";
import { digitador } from "../test/util.tsx";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthProvider.tsx";
import { API, servidor } from "../test/servidor.ts";
import { Registro } from "./Registro.tsx";

const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "novo@remind.local",
  name: "Novo",
  timezone: "America/Sao_Paulo",
  created_at: "2026-08-20T12:00:00Z",
};

function Onde() {
  return <p>rota: {useLocation().pathname}</p>;
}

function montar() {
  servidor.use(
    http.post(`${API}/auth/refresh/`, () => HttpResponse.json({}, { status: 401 })),
  );

  return render(
    <MemoryRouter initialEntries={["/registro"]}>
      <AuthProvider>
        <Routes>
          <Route path="/registro" element={<Registro />} />
          <Route path="*" element={<Onde />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function preencher() {
  const usuario = digitador();
  await usuario.type(screen.getByLabelText("E-mail"), "novo@remind.local");
  await usuario.type(screen.getByLabelText("Nome"), "Novo");
  await usuario.type(screen.getByLabelText("Senha"), "senha-de-teste-sem-valor");
  await usuario.click(screen.getByRole("button", { name: /criar conta/i }));
}

describe("Registro", () => {
  it("mostra o erro de senha fraca no campo de senha", async () => {
    servidor.use(
      http.post(`${API}/auth/register/`, () =>
        HttpResponse.json(
          { password: ["Esta senha é muito comum.", "Esta senha é curta demais."] },
          { status: 400 },
        ),
      ),
    );
    montar();
    await preencher();

    // O RegisterSerializer mapeia os AUTH_PASSWORD_VALIDATORS para `password`
    // de propósito — sem isso cairiam em `non_field_errors` e o usuário não
    // saberia qual campo corrigir. A tela precisa honrar esse mapeamento.
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Esta senha é muito comum.");
    expect(alerta).toHaveTextContent("Esta senha é curta demais.");
  });

  it("mostra o erro de e-mail já cadastrado no campo de e-mail", async () => {
    servidor.use(
      http.post(`${API}/auth/register/`, () =>
        HttpResponse.json(
          { email: ["Já existe uma conta com este e-mail."] },
          { status: 400 },
        ),
      ),
    );
    montar();
    await preencher();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Já existe uma conta com este e-mail.",
    );
  });

  it("entra automaticamente depois de criar a conta", async () => {
    servidor.use(
      http.post(`${API}/auth/register/`, () =>
        HttpResponse.json(USUARIO, { status: 201 }),
      ),
      http.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ access: "tok", user: USUARIO }),
      ),
    );
    montar();
    await preencher();

    // O cadastro não devolve token: a API separa criar conta de abrir sessão.
    // Obrigar a redigitar tudo na tela de login seria atrito sem motivo.
    expect(await screen.findByText("rota: /")).toBeInTheDocument();
  });

  it("envia o fuso do browser junto com o cadastro", async () => {
    let recebido: Record<string, unknown> | null = null;
    servidor.use(
      http.post(`${API}/auth/register/`, async ({ request }) => {
        recebido = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(USUARIO, { status: 201 });
      }),
      http.post(`${API}/auth/login/`, () =>
        HttpResponse.json({ access: "tok", user: USUARIO }),
      ),
    );
    montar();
    await preencher();

    // `users.timezone` decide o que é "hoje" para o status de vencimento
    // (RF10) e para o job de alertas. Deixar no padrão do servidor faria um
    // usuário em Lisboa ver o vencimento virar no horário de São Paulo.
    await screen.findByText("rota: /");
    expect(recebido).toHaveProperty("timezone");
    expect((recebido as unknown as { timezone: string }).timezone).toBeTruthy();
  });

  it("cai numa mensagem genérica quando o erro não é de validação", async () => {
    servidor.use(
      http.post(`${API}/auth/register/`, () => HttpResponse.json({}, { status: 500 })),
    );
    montar();
    await preencher();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível criar a conta",
    );
  });
});
