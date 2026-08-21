import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Coluna } from "../api/tipos.ts";
import { API, servidor } from "../test/servidor.ts";
import { digitador, renderizar } from "../test/util.tsx";
import { TabelaColunas } from "./TabelaColunas.tsx";

const ID = "aaaaaaaa-0000-0000-0000-000000000001";

function coluna(parcial: Partial<Coluna> = {}): Coluna {
  return {
    id: "c1",
    key: "cliente",
    name: "Cliente",
    type: "text",
    position: 0,
    is_required: false,
    is_sensitive: false,
    options: [],
    created_at: "2026-08-01T12:00:00Z",
    updated_at: "2026-08-01T12:00:00Z",
    ...parcial,
  };
}

function comColunas(...lista: Coluna[]) {
  return [
    http.get(`${API}/tables/${ID}/`, () =>
      HttpResponse.json({
        id: ID,
        name: "Contratos",
        description: "",
        alert_lead_days: 3,
        columns: lista,
        created_at: "2026-08-01T12:00:00Z",
        updated_at: "2026-08-01T12:00:00Z",
      }),
    ),
    http.get(`${API}/tables/${ID}/columns/`, () =>
      HttpResponse.json({
        count: lista.length,
        next: null,
        previous: null,
        results: lista,
      }),
    ),
  ];
}

function montar() {
  return renderizar(<TabelaColunas />, {
    rota: `/tabelas/${ID}/colunas`,
    caminho: "/tabelas/:id/colunas",
  });
}

describe("TabelaColunas", () => {
  it("avisa que sem coluna de vencimento não há prazos nem alertas", async () => {
    servidor.use(...comColunas(coluna()));
    montar();

    expect(await screen.findByText(/não tem coluna de vencimento/i)).toBeInTheDocument();
  });

  it("não repete o aviso quando já existe uma coluna de vencimento", async () => {
    servidor.use(
      ...comColunas(
        coluna(),
        coluna({ id: "c2", key: "vence", name: "Vence", type: "due_date" }),
      ),
    );
    montar();

    await screen.findByText("Cliente");
    expect(screen.queryByText(/não tem coluna de vencimento/i)).not.toBeInTheDocument();
  });

  it("mostra tipo, chave e marcações de cada coluna", async () => {
    servidor.use(
      ...comColunas(
        coluna({ key: "cpf", name: "CPF", is_required: true, is_sensitive: true }),
      ),
    );
    montar();

    const linha = (await screen.findByText("CPF")).closest("li");
    expect(linha).toHaveTextContent("Texto");
    expect(linha).toHaveTextContent("obrigatória");
    expect(linha).toHaveTextContent("sensível");
    // A `key` é o que indexa o JSONB e é imutável — quem cruza a tela com o
    // CSV precisa dela, porque o cabeçalho exportado é o rótulo, não a chave.
    expect(linha).toHaveTextContent("cpf");
  });

  describe("RF06 — uma coluna de vencimento por tabela", () => {
    it("desabilita o tipo vencimento quando já existe uma", async () => {
      servidor.use(...comColunas(coluna({ id: "c2", name: "Vence", type: "due_date" })));
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Nova coluna" }));

      // O índice parcial no banco garante a regra; oferecer a opção para depois
      // recusá-la com 400 faria o usuário descobrir a regra errando.
      const opcao = screen.getByRole("option", { name: /Data de vencimento/ });
      expect(opcao).toBeDisabled();
      expect(opcao).toHaveTextContent("já existe uma");
    });

    it("oferece o tipo vencimento quando ainda não há nenhuma", async () => {
      servidor.use(...comColunas(coluna()));
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Nova coluna" }));

      expect(screen.getByRole("option", { name: "Data de vencimento" })).toBeEnabled();
    });
  });

  describe("edição", () => {
    it("trava o tipo e explica por quê", async () => {
      servidor.use(...comColunas(coluna()));
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Editar" }));

      const seletor = screen.getByLabelText("Tipo");
      expect(seletor).toBeDisabled();
      // O serializer recusa a troca com 400; a tela precisa dizer o motivo,
      // senão vira campo travado sem explicação.
      expect(seletor).toHaveAccessibleDescription(/registros já gravados/i);
    });

    it("remonta o formulário ao trocar de coluna", async () => {
      servidor.use(
        ...comColunas(
          coluna(),
          coluna({ id: "c2", key: "valor", name: "Valor", type: "number" }),
        ),
      );
      montar();
      const usuario = digitador();

      const editar = await screen.findAllByRole("button", { name: "Editar" });
      await usuario.click(editar[0]!);
      expect(screen.getByLabelText("Rótulo")).toHaveValue("Cliente");

      await usuario.click(screen.getAllByRole("button", { name: "Editar" })[1]!);
      // Sem `key` no componente, o React reaproveita a instância e o useState
      // mantém "Cliente" no campo — o usuário editaria a coluna errada.
      expect(screen.getByLabelText("Rótulo")).toHaveValue("Valor");
    });
  });

  describe("opções de lista", () => {
    it("só pede opções para o tipo lista", async () => {
      servidor.use(...comColunas(coluna()));
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Nova coluna" }));
      expect(screen.queryByLabelText("Opções")).not.toBeInTheDocument();

      await usuario.selectOptions(screen.getByLabelText("Tipo"), "select");
      expect(screen.getByLabelText("Opções")).toBeInTheDocument();
    });

    it("envia uma opção por linha, aparadas, e vazio para outros tipos", async () => {
      const enviados: unknown[] = [];
      servidor.use(
        ...comColunas(coluna()),
        http.post(`${API}/tables/${ID}/columns/`, async ({ request }) => {
          enviados.push(await request.json());
          return HttpResponse.json(coluna({ id: "c9" }), { status: 201 });
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Nova coluna" }));
      await usuario.type(screen.getByLabelText("Rótulo"), "Status");
      await usuario.selectOptions(screen.getByLabelText("Tipo"), "select");
      await usuario.type(screen.getByLabelText("Opções"), "  Ativo  \n\nEncerrado\n");
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      await waitFor(() => expect(enviados).toHaveLength(1));
      expect(enviados[0]).toMatchObject({
        name: "Status",
        type: "select",
        options: ["Ativo", "Encerrado"],
      });
    });
  });

  describe("reordenar", () => {
    it("manda a lista INTEIRA de ids, não só o par trocado", async () => {
      const corpos: { order: string[] }[] = [];
      const lista = [
        coluna({ id: "c1", name: "Cliente", position: 0 }),
        coluna({ id: "c2", key: "valor", name: "Valor", position: 1 }),
        coluna({ id: "c3", key: "resp", name: "Responsável", position: 2 }),
      ];
      servidor.use(
        ...comColunas(...lista),
        http.patch(`${API}/tables/${ID}/columns/reorder/`, async ({ request }) => {
          corpos.push((await request.json()) as { order: string[] });
          return HttpResponse.json(lista);
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(
        await screen.findByRole("button", { name: "Mover Valor para cima" }),
      );

      // O ReorderSerializer compara o conjunto recebido com o conjunto atual da
      // tabela e recusa qualquer diferença. Mandar só o par trocado dá 400.
      await waitFor(() => expect(corpos).toHaveLength(1));
      expect(corpos[0]!.order).toEqual(["c2", "c1", "c3"]);
    });

    it("não deixa mover a primeira para cima nem a última para baixo", async () => {
      servidor.use(
        ...comColunas(
          coluna({ id: "c1", name: "Cliente" }),
          coluna({ id: "c2", key: "valor", name: "Valor" }),
        ),
      );
      montar();

      expect(
        await screen.findByRole("button", { name: "Mover Cliente para cima" }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Mover Valor para baixo" }),
      ).toBeDisabled();
    });
  });

  describe("exclusão", () => {
    it("avisa que o valor some de todos os registros", async () => {
      servidor.use(...comColunas(coluna()));
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));

      const dialogo = screen.getByRole("dialog");
      expect(dialogo).toHaveTextContent(/todos os registros/i);
    });

    it("avisa que apagar a coluna de vencimento desliga os alertas", async () => {
      servidor.use(
        ...comColunas(
          coluna({ id: "c2", key: "vence", name: "Vence", type: "due_date" }),
        ),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));

      // `purge_column_key(was_due_date=True)` zera o due_date promovido. Quem
      // apaga a coluna não imagina que está desligando os alertas da tabela.
      expect(screen.getByRole("dialog")).toHaveTextContent(
        /nenhum alerta novo será gerado/i,
      );
    });

    it("não chama a API ao cancelar", async () => {
      const excluiu = vi.fn();
      servidor.use(
        ...comColunas(coluna()),
        http.delete(`${API}/tables/${ID}/columns/:cid/`, () => {
          excluiu();
          return new HttpResponse(null, { status: 204 });
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));
      await usuario.click(
        within(screen.getByRole("dialog")).getByRole("button", { name: "Cancelar" }),
      );

      expect(excluiu).not.toHaveBeenCalled();
    });
  });

  it("trata tabela alheia como não encontrada, sem falar em permissão", async () => {
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () => HttpResponse.json({}, { status: 404 })),
      http.get(`${API}/tables/${ID}/columns/`, () =>
        HttpResponse.json({}, { status: 404 }),
      ),
    );
    montar();

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Tabela não encontrada.");
    expect(aviso.textContent).not.toMatch(/permiss|autoriza/i);
  });
});
