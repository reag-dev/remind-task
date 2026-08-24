import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { RegraDeAlerta } from "../api/tipos.ts";
import { API, servidor } from "../test/servidor.ts";
import { digitador, renderizar } from "../test/util.tsx";
import { TabelaRegras } from "./TabelaRegras.tsx";

const ID = "aaaaaaaa-0000-0000-0000-000000000001";

function regra(parcial: Partial<RegraDeAlerta> = {}): RegraDeAlerta {
  return {
    id: "g1",
    offset_days: 3,
    channel: "in_app",
    is_active: true,
    created_at: "2026-08-01T12:00:00Z",
    updated_at: "2026-08-01T12:00:00Z",
    ...parcial,
  };
}

function cenario(regras: RegraDeAlerta[] = [regra()], leadDays = 3) {
  return [
    http.get(`${API}/tables/${ID}/`, () =>
      HttpResponse.json({
        id: ID,
        name: "Contratos",
        description: "",
        alert_lead_days: leadDays,
        columns: [],
        created_at: "2026-08-01T12:00:00Z",
        updated_at: "2026-08-01T12:00:00Z",
      }),
    ),
    http.get(`${API}/tables/${ID}/alert-rules/`, () =>
      HttpResponse.json({
        count: regras.length,
        next: null,
        previous: null,
        results: regras,
      }),
    ),
  ];
}

function montar() {
  return renderizar(<TabelaRegras />, {
    rota: `/tabelas/${ID}/alertas`,
    caminho: "/tabelas/:id/alertas",
  });
}

describe("TabelaRegras", () => {
  it("separa o indicador visual do disparo de notificacao", async () => {
    servidor.use(...cenario());
    montar();

    // `alert_lead_days` e `offset_days` sao confundidos o tempo todo porque os
    // dois se chamam "antecedencia". A consequencia de confundir e real: mexer
    // no limiar visual achando que se esta mexendo no disparo do alerta.
    expect(
      await screen.findByRole("heading", { name: "Indicador visual" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/não gera notificação/)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Regras de notificação" }),
    ).toBeInTheDocument();
  });

  describe("descricao das regras", () => {
    it.each([
      [3, "3 dias antes do vencimento"],
      [1, "1 dia antes do vencimento"],
      [0, "No dia do vencimento"],
      [-1, "1 dia depois do vencimento"],
      [-5, "5 dias depois do vencimento"],
    ])("descreve offset %i em portugues", async (dias, esperado) => {
      servidor.use(...cenario([regra({ offset_days: dias })]));
      montar();

      // `-1` como "1 dia depois" e o caso que justifica traduzir: o numero cru
      // nao diz que offset negativo serve para cobrar atraso.
      expect(await screen.findByText(esperado)).toBeInTheDocument();
    });
  });

  it("avisa que tabela sem regra nao gera alerta nenhum", async () => {
    servidor.use(...cenario([]));
    montar();

    expect(await screen.findByText(/nenhum alerta será gerado/i)).toBeInTheDocument();
  });

  it("mostra a mensagem do backend quando a regra ja existe", async () => {
    servidor.use(
      ...cenario(),
      http.post(`${API}/tables/${ID}/alert-rules/`, () =>
        HttpResponse.json(
          ["Já existe uma regra com essa antecedência e canal nesta tabela."],
          { status: 400 },
        ),
      ),
    );
    montar();
    const usuario = digitador();

    await usuario.type(await screen.findByLabelText("Nova regra (dias)"), "3");
    await usuario.click(screen.getByRole("button", { name: "Adicionar" }));

    // A unicidade e garantida por `alert_rules_unique` no banco; reescrever a
    // regra aqui criaria uma segunda copia que sairia de sincronia.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  // Este teste exigia o oposto ate a Phase 5: que `channel` NAO fosse enviado,
  // porque a entrega por e-mail nao existia e escolher `email` criaria uma
  // regra que nunca dispara nada. Foi reescrito, e nao remendado — a premissa
  // dele morreu quando `alerts.send_pending_emails` passou a entregar.
  it("envia o canal escolhido", async () => {
    let corpo: Record<string, unknown> | null = null;
    servidor.use(
      ...cenario(),
      http.post(`${API}/tables/${ID}/alert-rules/`, async ({ request }) => {
        corpo = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(regra({ id: "g2", offset_days: 7 }), { status: 201 });
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.type(await screen.findByLabelText("Nova regra (dias)"), "7");
    await usuario.selectOptions(screen.getByLabelText("Onde avisar"), "email");
    await usuario.click(screen.getByRole("button", { name: "Adicionar" }));

    await waitFor(() => expect(corpo).toEqual({ offset_days: 7, channel: "email" }));
  });

  it("avisa o que o e-mail leva antes de o usuario escolher", async () => {
    // Um e-mail sai do sistema e fica na caixa de entrada de alguem para
    // sempre. Dizer o que ele carrega e o que permite decidir com informacao —
    // e o aviso so faz sentido quando o canal esta selecionado.
    servidor.use(...cenario());
    montar();
    const usuario = digitador();

    await screen.findByLabelText("Onde avisar");
    expect(screen.queryByText(/Colunas marcadas como sensiveis/i)).toBeNull();

    await usuario.selectOptions(screen.getByLabelText("Onde avisar"), "email");

    expect(screen.getByText(/nunca aparecem/i)).toBeInTheDocument();
  });

  it("aceita antecedencia negativa para cobrar atraso", async () => {
    let corpo: Record<string, unknown> | null = null;
    servidor.use(
      ...cenario(),
      http.post(`${API}/tables/${ID}/alert-rules/`, async ({ request }) => {
        corpo = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(regra({ id: "g3", offset_days: -2 }), { status: 201 });
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.type(await screen.findByLabelText("Nova regra (dias)"), "-2");
    await usuario.click(screen.getByRole("button", { name: "Adicionar" }));

    // `in_app` e o default do seletor — o canal vai junto sem o usuario mexer.
    await waitFor(() => expect(corpo).toEqual({ offset_days: -2, channel: "in_app" }));
  });

  it("ativa e desativa uma regra sem apaga-la", async () => {
    let corpo: Record<string, unknown> | null = null;
    servidor.use(
      ...cenario(),
      http.patch(`${API}/tables/${ID}/alert-rules/g1/`, async ({ request }) => {
        corpo = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(regra({ is_active: false }));
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.click(await screen.findByRole("button", { name: "Desativar" }));

    // Desativar preserva o historico de alertas gerados; remover apaga em
    // cascata. Sao acoes diferentes de propósito.
    await waitFor(() => expect(corpo).toEqual({ is_active: false }));
  });

  it("remove uma regra", async () => {
    const removeu = vi.fn();
    servidor.use(
      ...cenario(),
      http.delete(`${API}/tables/${ID}/alert-rules/g1/`, () => {
        removeu();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.click(await screen.findByRole("button", { name: "Remover" }));

    await waitFor(() => expect(removeu).toHaveBeenCalledTimes(1));
  });

  it("salva o limiar visual na tabela, nao numa regra", async () => {
    let corpo: Record<string, unknown> | null = null;
    servidor.use(
      ...cenario(),
      http.patch(`${API}/tables/${ID}/`, async ({ request }) => {
        corpo = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({});
      }),
    );
    montar();
    const usuario = digitador();

    const campo = await screen.findByLabelText("Dias de antecedência do indicador");
    await usuario.clear(campo);
    await usuario.type(campo, "10");
    await usuario.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(corpo).toEqual({ alert_lead_days: 10 }));
  });

  it("trata tabela alheia como nao encontrada", async () => {
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () => HttpResponse.json({}, { status: 404 })),
      http.get(`${API}/tables/${ID}/alert-rules/`, () =>
        HttpResponse.json({}, { status: 404 }),
      ),
    );
    montar();

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Tabela não encontrada.");
    expect(aviso.textContent).not.toMatch(/permiss|autoriza/i);
  });
});
