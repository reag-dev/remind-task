import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Coluna } from "../api/tipos.ts";
import { API, servidor } from "../test/servidor.ts";
import { renderizar } from "../test/util.tsx";
import { ListaColunas } from "./ListaColunas.tsx";

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

function montar(colunas: Coluna[]) {
  return renderizar(
    <ListaColunas tabelaId={ID} colunas={colunas} onEditar={vi.fn()} />,
  );
}

describe("ListaColunas", () => {
  it("explica a consequência de não ter coluna nenhuma", () => {
    montar([]);

    // Não é um "nada aqui" decorativo: sem coluna, o POST de registro não tem
    // onde gravar valor, e a tabela é inútil.
    expect(screen.getByText(/não é possível inserir registros/i)).toBeInTheDocument();
  });

  it("lista as opções de uma coluna do tipo lista", () => {
    montar([coluna({ type: "select", options: ["Ativo", "Encerrado"] })]);

    expect(screen.getByText("Opções: Ativo, Encerrado")).toBeInTheDocument();
  });

  it("avisa quando a reordenação falha", async () => {
    servidor.use(
      http.patch(`${API}/tables/${ID}/columns/reorder/`, () =>
        HttpResponse.json({ detail: "não deu" }, { status: 400 }),
      ),
    );
    montar([coluna(), coluna({ id: "c2", key: "valor", name: "Valor" })]);
    const usuario = userEvent.setup();

    await usuario.click(screen.getByRole("button", { name: "Mover Valor para cima" }));

    // Falha silenciosa aqui é pior que em outros lugares: a lista volta à ordem
    // antiga na revalidação e parece que o clique não registrou.
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível reordenar",
    );
  });

  it("fecha o diálogo depois de excluir com sucesso", async () => {
    servidor.use(
      http.delete(
        `${API}/tables/${ID}/columns/c1/`,
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    montar([coluna()]);
    const usuario = userEvent.setup();

    await usuario.click(screen.getByRole("button", { name: "Excluir" }));
    await usuario.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir" }),
    );

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("mantém o diálogo aberto e avisa quando a exclusão falha", async () => {
    servidor.use(
      http.delete(`${API}/tables/${ID}/columns/c1/`, () =>
        HttpResponse.json({ detail: "não" }, { status: 500 }),
      ),
    );
    montar([coluna()]);
    const usuario = userEvent.setup();

    await usuario.click(screen.getByRole("button", { name: "Excluir" }));
    const dialogo = screen.getByRole("dialog");
    await usuario.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    // Fechar o diálogo num erro faria parecer que a exclusão funcionou.
    expect(await within(dialogo).findByRole("alert")).toHaveTextContent(
      "Não foi possível excluir",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("desabilita as setas enquanto a reordenação está em voo", async () => {
    servidor.use(
      http.patch(`${API}/tables/${ID}/columns/reorder/`, async () => {
        await new Promise((resolver) => setTimeout(resolver, 50));
        return HttpResponse.json([]);
      }),
    );
    montar([coluna(), coluna({ id: "c2", key: "valor", name: "Valor" })]);
    const usuario = userEvent.setup();

    await usuario.click(screen.getByRole("button", { name: "Mover Valor para cima" }));

    // Dois cliques rápidos enviariam duas permutações calculadas sobre a MESMA
    // lista antiga — a segunda desfaria a primeira.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Mover Cliente para baixo" })).toBeDisabled();
    });
  });
});
