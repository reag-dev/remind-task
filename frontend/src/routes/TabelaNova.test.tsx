import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { renderizar } from "../test/util.tsx";
import { TabelaNova } from "./TabelaNova.tsx";

const CRIADA = {
  id: "aaaaaaaa-0000-0000-0000-000000000009",
  name: "Contratos",
  description: "",
  alert_lead_days: 3,
  columns: [],
  created_at: "2026-08-20T12:00:00Z",
  updated_at: "2026-08-20T12:00:00Z",
};

describe("TabelaNova", () => {
  it("não deixa enviar sem nome", () => {
    renderizar(<TabelaNova />, { rota: "/tabelas/nova" });

    expect(screen.getByRole("button", { name: /criar tabela/i })).toBeDisabled();
  });

  it("envia os campos aparados e leva para a tabela criada", async () => {
    let recebido: Record<string, unknown> | null = null;
    servidor.use(
      http.post(`${API}/tables/`, async ({ request }) => {
        recebido = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(CRIADA, { status: 201 });
      }),
    );
    renderizar(<TabelaNova />, { rota: "/tabelas/nova" });
    const usuario = userEvent.setup();

    await usuario.type(screen.getByLabelText("Nome"), "  Contratos  ");
    await usuario.click(screen.getByRole("button", { name: /criar tabela/i }));

    // Ir direto para a tabela CRIADA, e não voltar para a lista: uma tabela sem
    // colunas não aceita registro nenhum, então definir colunas é o próximo
    // passo obrigatório. Asserir o id devolvido pela API é o que distingue
    // "navegou" de "navegou para o lugar certo".
    expect(await screen.findByText(`rota: /tabelas/${CRIADA.id}`)).toBeInTheDocument();
    expect(recebido).toMatchObject({ name: "Contratos", alert_lead_days: 3 });
  });

  it("mostra o erro de nome duplicado no campo", async () => {
    servidor.use(
      http.post(`${API}/tables/`, () =>
        HttpResponse.json(
          { name: ["Você já tem uma tabela com esse nome."] },
          { status: 400 },
        ),
      ),
    );
    renderizar(<TabelaNova />, { rota: "/tabelas/nova" });
    const usuario = userEvent.setup();

    await usuario.type(screen.getByLabelText("Nome"), "Contratos");
    await usuario.click(screen.getByRole("button", { name: /criar tabela/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Você já tem uma tabela com esse nome.",
    );
  });

  it("separa antecedência de regra de alerta na ajuda do campo", () => {
    renderizar(<TabelaNova />, { rota: "/tabelas/nova" });

    // `alert_lead_days` controla o indicador visual (RF10); as regras de
    // antecedência controlam o disparo da notificação (RF12). Sem esta
    // distinção explícita os dois viram sinônimos para quem usa.
    const campo = screen.getByLabelText(/próximo do vencimento/i);
    expect(campo).toHaveAccessibleDescription(/não confunda com as regras de alerta/i);
  });

  it("cai numa mensagem genérica quando o erro não é de validação", async () => {
    servidor.use(
      http.post(`${API}/tables/`, () => HttpResponse.json({}, { status: 500 })),
    );
    renderizar(<TabelaNova />, { rota: "/tabelas/nova" });
    const usuario = userEvent.setup();

    await usuario.type(screen.getByLabelText("Nome"), "Contratos");
    await usuario.click(screen.getByRole("button", { name: /criar tabela/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível criar a tabela",
    );
  });
});
