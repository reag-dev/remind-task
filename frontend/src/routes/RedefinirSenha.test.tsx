import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { digitador } from "../test/util.tsx";
import { RedefinirSenha } from "./RedefinirSenha.tsx";

const LINK = "/redefinir-senha?uid=Zm9v&token=abc-123";

function Onde() {
  const { pathname, search } = useLocation();
  return <p>rota: {pathname + search}</p>;
}

function montar(entrada = LINK) {
  return render(
    <MemoryRouter initialEntries={[entrada]}>
      <Routes>
        <Route path="/redefinir-senha" element={<RedefinirSenha />} />
        <Route path="*" element={<Onde />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function salvar(senha = "senha-de-teste-sem-valor") {
  const usuario = digitador();
  await usuario.type(screen.getByLabelText("Nova senha"), senha);
  await usuario.click(screen.getByRole("button", { name: /salvar senha/i }));
}

describe("RedefinirSenha", () => {
  it("manda para o login com aviso depois de trocar a senha", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/confirm/`, () => new HttpResponse(null, { status: 204 })),
    );
    montar();
    await salvar();

    // A API devolve 204, sem corpo. Sem a marca na URL o usuário sairia de uma
    // tela que dizia "salvando" e cairia num login mudo.
    expect(await screen.findByText("rota: /login?redefinida=1")).toBeInTheDocument();
  });

  it("envia o uid e o token que vieram na URL", async () => {
    let recebido: Record<string, unknown> | null = null;
    servidor.use(
      http.post(`${API}/auth/password-reset/confirm/`, async ({ request }) => {
        recebido = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    montar();
    await salvar();

    await screen.findByText(/rota: \/login/);
    expect(recebido).toMatchObject({ uid: "Zm9v", token: "abc-123" });
  });

  it("recusa o link incompleto antes de pedir a senha", () => {
    // O caminho mais comum de chegar aqui sem os parâmetros é um cliente de
    // e-mail que quebrou a URL em duas linhas. Pedir uma senha para só então
    // dizer "link inválido" seria cruel sem motivo.
    montar("/redefinir-senha?uid=Zm9v");

    expect(screen.getByRole("alert")).toHaveTextContent(/incompleto/i);
    expect(screen.queryByLabelText("Nova senha")).not.toBeInTheDocument();
  });

  it("trata token recusado como link morto, sem distinguir o motivo", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/confirm/`, () =>
        HttpResponse.json({ token: ["Link inválido ou expirado. Peça um novo."] }, { status: 400 }),
      ),
    );
    montar();
    await salvar();

    // O backend não separa "uid desconhecido" de "token errado" — os dois viram
    // erro em `token`, para não contar quais contas existem. A tela segue a
    // mesma regra.
    expect(await screen.findByRole("alert")).toHaveTextContent(/expirou ou já foi usado/i);
    expect(screen.getByRole("link", { name: /pedir novo link/i })).toBeInTheDocument();
  });

  it("mostra os erros dos validadores no campo de senha", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/confirm/`, () =>
        HttpResponse.json(
          { password: ["Esta senha é muito comum.", "Esta senha é curta demais."] },
          { status: 400 },
        ),
      ),
    );
    montar();
    await salvar("123");

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Esta senha é muito comum.");
    expect(alerta).toHaveTextContent("Esta senha é curta demais.");
    // Senha fraca não pode ser confundida com link morto: o usuário ainda tem
    // um link válido nas mãos e precisa continuar no formulário.
    expect(screen.getByLabelText("Nova senha")).toBeInTheDocument();
  });
});
