import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { digitador, renderizar } from "../test/util.tsx";
import { Tabelas } from "./Tabelas.tsx";

function tabela(parcial: Partial<Record<string, unknown>> = {}) {
  return {
    id: "aaaaaaaa-0000-0000-0000-000000000001",
    name: "Contratos",
    description: "",
    alert_lead_days: 3,
    columns: [{ id: "c1" }, { id: "c2" }],
    created_at: "2026-08-01T12:00:00Z",
    updated_at: "2026-08-01T12:00:00Z",
    ...parcial,
  };
}

function listaCom(...itens: unknown[]) {
  return http.get(`${API}/tables/`, () =>
    HttpResponse.json({
      count: itens.length,
      next: null,
      previous: null,
      results: itens,
    }),
  );
}

describe("Tabelas", () => {
  it("lista as tabelas com contagem de colunas e antecedência", async () => {
    servidor.use(listaCom(tabela()));
    renderizar(<Tabelas />);

    expect(await screen.findByRole("link", { name: "Contratos" })).toBeInTheDocument();
    expect(screen.getByText(/2 colunas/)).toBeInTheDocument();
    expect(screen.getByText(/3 dias antes/)).toBeInTheDocument();
  });

  it("usa singular quando há uma coluna só", async () => {
    servidor.use(listaCom(tabela({ columns: [{ id: "c1" }], alert_lead_days: 1 })));
    renderizar(<Tabelas />);

    expect(await screen.findByText(/1 coluna ·/)).toBeInTheDocument();
    expect(screen.getByText(/1 dia antes/)).toBeInTheDocument();
  });

  it("convida a criar a primeira quando não há nenhuma", async () => {
    servidor.use(listaCom());
    renderizar(<Tabelas />);

    expect(await screen.findByText(/Nenhuma tabela ainda/)).toBeInTheDocument();
  });

  it("mostra erro recuperável quando a listagem falha", async () => {
    servidor.use(
      http.get(`${API}/tables/`, () => HttpResponse.json({}, { status: 500 })),
    );
    renderizar(<Tabelas />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar suas tabelas",
    );
    expect(screen.getByRole("button", { name: /tentar de novo/i })).toBeInTheDocument();
  });

  describe("exclusão", () => {
    it("nomeia a tabela e avisa da cascata antes de confirmar", async () => {
      servidor.use(listaCom(tabela()));
      renderizar(<Tabelas />);
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));

      const dialogo = screen.getByRole("dialog");
      // Confirmação genérica não deixa perceber o clique na linha errada, e a
      // exclusão leva junto colunas, registros e alertas.
      expect(within(dialogo).getByText("Contratos")).toBeInTheDocument();
      expect(dialogo).toHaveTextContent(/registros e os alertas/);
      expect(dialogo).toHaveTextContent(/Não há como desfazer/);
    });

    it("não chama a API se o usuário cancelar", async () => {
      const excluiu = vi.fn();
      servidor.use(
        listaCom(tabela()),
        http.delete(`${API}/tables/:id/`, () => {
          excluiu();
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderizar(<Tabelas />);
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));
      await usuario.click(screen.getByRole("button", { name: "Cancelar" }));

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
      expect(excluiu).not.toHaveBeenCalled();
    });

    it("exclui e recarrega a lista ao confirmar", async () => {
      let restantes: unknown[] = [tabela()];
      servidor.use(
        http.get(`${API}/tables/`, () =>
          HttpResponse.json({
            count: restantes.length,
            next: null,
            previous: null,
            results: restantes,
          }),
        ),
        http.delete(`${API}/tables/:id/`, () => {
          restantes = [];
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderizar(<Tabelas />);
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));
      await usuario.click(
        within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir" }),
      );

      // A lista precisa refletir a exclusão sem F5: é a invalidação da chave
      // que faz isso, e ela some fácil num refactor.
      expect(await screen.findByText(/Nenhuma tabela ainda/)).toBeInTheDocument();
    });
  });

  describe("renomear", () => {
    it("mostra a mensagem do backend quando o nome já existe", async () => {
      servidor.use(
        listaCom(tabela()),
        http.patch(`${API}/tables/:id/`, () =>
          HttpResponse.json(
            { name: ["Você já tem uma tabela com esse nome."] },
            { status: 400 },
          ),
        ),
      );
      renderizar(<Tabelas />);
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Renomear" }));
      await usuario.clear(screen.getByLabelText("Nome da tabela"));
      await usuario.type(screen.getByLabelText("Nome da tabela"), "Outra");
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      // A regra de unicidade mora no banco (tables_unique_name_per_user).
      // Reescrevê-la aqui criaria uma segunda cópia, que sairia de sincronia.
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Você já tem uma tabela com esse nome.",
      );
    });

    it("salva o nome novo e volta para a visualização", async () => {
      const enviados: string[] = [];
      let atual = tabela();
      servidor.use(
        http.get(`${API}/tables/`, () =>
          HttpResponse.json({ count: 1, next: null, previous: null, results: [atual] }),
        ),
        http.patch(`${API}/tables/:id/`, async ({ request }) => {
          const corpo = (await request.json()) as { name: string };
          enviados.push(corpo.name);
          atual = tabela({ name: corpo.name });
          return HttpResponse.json(atual);
        }),
      );
      renderizar(<Tabelas />);
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Renomear" }));
      await usuario.clear(screen.getByLabelText("Nome da tabela"));
      await usuario.type(
        screen.getByLabelText("Nome da tabela", { exact: true }),
        "  Licenças  ",
      );
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      expect(await screen.findByRole("link", { name: "Licenças" })).toBeInTheDocument();
      // Espaço nas pontas some antes de sair: o backend também apara, e enviar
      // com espaço faria o nome "  A  " e "A" competirem pela unicidade.
      expect(enviados).toEqual(["Licenças"]);
    });
  });
});
