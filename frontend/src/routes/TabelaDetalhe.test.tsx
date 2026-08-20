import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { renderizar } from "../test/util.tsx";
import { TabelaDetalhe } from "./TabelaDetalhe.tsx";

const ID = "aaaaaaaa-0000-0000-0000-000000000001";

function montar() {
  return renderizar(<TabelaDetalhe />, {
    rota: `/tabelas/${ID}`,
    caminho: "/tabelas/:id",
  });
}

describe("TabelaDetalhe", () => {
  it("mostra o nome e a descrição da tabela", async () => {
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () =>
        HttpResponse.json({
          id: ID,
          name: "Contratos",
          description: "Contratos de prestação de serviço",
          alert_lead_days: 3,
          columns: [],
          created_at: "2026-08-01T12:00:00Z",
          updated_at: "2026-08-01T12:00:00Z",
        }),
      ),
    );
    montar();

    expect(await screen.findByRole("heading", { name: "Contratos" })).toBeInTheDocument();
    expect(screen.getByText("Contratos de prestação de serviço")).toBeInTheDocument();
  });

  it("nunca diz 'sem permissão' para uma tabela de outro dono", async () => {
    // O backend responde 404 tanto para tabela inexistente quanto para tabela
    // alheia — deliberado (RS04), porque 403 confirmaria que o recurso existe.
    // A interface tem de respeitar isso: dizer "sem permissão" aqui
    // reintroduziria na tela o vazamento que a API gastou uma suíte para
    // evitar (tests/security/test_cross_tenant.py).
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () =>
        HttpResponse.json({ detail: "Não encontrado." }, { status: 404 }),
      ),
    );
    montar();

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Tabela não encontrada.");
    expect(aviso.textContent).not.toMatch(/permiss|autoriza|acesso negado/i);
  });

  it("distingue falha de servidor de tabela inexistente", async () => {
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () => HttpResponse.json({}, { status: 500 })),
    );
    montar();

    // 500 não é "não encontrada": mandar o usuário embora achando que a tabela
    // sumiu, quando o banco só piscou, é pior que mostrar o erro.
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a tabela.",
    );
  });
});
