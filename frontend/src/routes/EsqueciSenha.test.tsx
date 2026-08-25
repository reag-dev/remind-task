import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { digitador } from "../test/util.tsx";
import { EsqueciSenha } from "./EsqueciSenha.tsx";

function montar() {
  return render(
    <MemoryRouter initialEntries={["/esqueci-senha"]}>
      <EsqueciSenha />
    </MemoryRouter>,
  );
}

async function pedir(email = "ana@remind.local") {
  const usuario = digitador();
  await usuario.type(screen.getByLabelText("E-mail"), email);
  await usuario.click(screen.getByRole("button", { name: /enviar link/i }));
}

describe("EsqueciSenha", () => {
  it("confirma o envio sem dizer se a conta existe", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/`, () => new HttpResponse(null, { status: 204 })),
    );
    montar();
    await pedir();

    // A API responde 204 exista ou não a conta. Escrever "enviamos para o seu
    // e-mail" contra "não encontramos esse e-mail" recriaria no cliente o
    // oráculo de cadastro que o servidor recusa ser — por isso a redação é
    // condicional na FORMA.
    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent(/se houver uma conta/i);
  });

  it("mostra a mesma tela para um e-mail sem cadastro", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/`, () => new HttpResponse(null, { status: 204 })),
    );
    montar();
    await pedir("ninguem@remind.local");

    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent(/se houver uma conta/i);
    expect(aviso).not.toHaveTextContent(/não encontr/i);
  });

  it("explica o limite de pedidos quando leva 429", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/`, () =>
        HttpResponse.json({ detail: "Request was throttled." }, { status: 429 }),
      ),
    );
    montar();
    await pedir();

    // Sem mensagem própria, o usuário repete o pedido e continua batendo na
    // parede — o teto é por IP e dura uma hora.
    expect(await screen.findByRole("alert")).toHaveTextContent(/muitos pedidos/i);
  });

  it("cai numa mensagem de conexão quando o servidor não responde", async () => {
    servidor.use(
      http.post(`${API}/auth/password-reset/`, () => HttpResponse.error()),
    );
    montar();
    await pedir();

    expect(await screen.findByRole("alert")).toHaveTextContent(/servidor/i);
  });
});
