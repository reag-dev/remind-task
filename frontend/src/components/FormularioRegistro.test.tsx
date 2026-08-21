import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Coluna, Registro } from "../api/tipos.ts";
import { API, servidor } from "../test/servidor.ts";
import { digitador, renderizar } from "../test/util.tsx";
import { FormularioRegistro } from "./FormularioRegistro.tsx";

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

const REGISTRO: Registro = {
  id: "r1",
  data: { cliente: "Empresa A" },
  due_date: null,
  due_status: "no_due",
  days_until_due: null,
  position: null,
  created_at: "2026-08-01T12:00:00Z",
  updated_at: "2026-08-01T12:00:00Z",
};

function montar(colunas: Coluna[], registro?: Registro) {
  return renderizar(
    <FormularioRegistro
      tabelaId={ID}
      colunas={colunas}
      registro={registro}
      onSair={vi.fn()}
    />,
  );
}

/** Captura o `data` enviado no POST. */
function capturarPost() {
  const enviados: { data: Record<string, unknown> }[] = [];
  servidor.use(
    http.post(`${API}/tables/${ID}/records/`, async ({ request }) => {
      enviados.push((await request.json()) as { data: Record<string, unknown> });
      return HttpResponse.json(REGISTRO, { status: 201 });
    }),
  );
  return enviados;
}

describe("FormularioRegistro", () => {
  it("monta um campo por coluna, com o input adequado ao tipo", () => {
    montar([
      coluna({ id: "c1", key: "cliente", name: "Cliente", type: "text" }),
      coluna({ id: "c2", key: "vence", name: "Vence", type: "due_date" }),
      coluna({ id: "c3", key: "ativo", name: "Ativo", type: "boolean" }),
      coluna({ id: "c4", key: "email", name: "E-mail", type: "email" }),
    ]);

    expect(screen.getByLabelText("Cliente")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Vence")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("Ativo")).toHaveAttribute("type", "checkbox");
    expect(screen.getByLabelText("E-mail")).toHaveAttribute("type", "email");
  });

  it("marca coluna obrigatoria de forma acessivel", () => {
    montar([coluna({ is_required: true })]);

    // O asterisco sozinho e `aria-hidden`; quem usa leitor de tela ouve a
    // palavra. Um `*` visual e invisivel para quem nao ve.
    expect(screen.getByLabelText(/Cliente.*obrigatório/s)).toBeInTheDocument();
  });

  it("oferece opcao vazia numa coluna de lista", () => {
    montar([coluna({ type: "select", options: ["Ativo", "Encerrado"] })]);

    // Sem a opcao vazia, o primeiro item viraria o valor de fato e uma coluna
    // opcional ficaria impossivel de deixar em branco.
    const seletor = screen.getByLabelText("Cliente");
    expect(within_options(seletor)).toEqual(["—", "Ativo", "Encerrado"]);
  });

  it("nao usa type=password em coluna sensivel", () => {
    montar([coluna({ is_sensitive: true })]);

    // RS05 protege exibicao em lista, log e alerta — nao o proprio dono
    // conferindo o que acabou de digitar.
    expect(screen.getByLabelText("Cliente")).toHaveAttribute("type", "text");
  });

  describe("conversao de valores", () => {
    it("envia null para campo vazio, e nao a chave ausente", async () => {
      const enviados = capturarPost();
      montar([coluna(), coluna({ id: "c2", key: "obs", name: "Obs" })]);
      const usuario = digitador();

      await usuario.type(screen.getByLabelText("Cliente"), "Empresa A");
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      await waitFor(() => expect(enviados).toHaveLength(1));
      // Omitir a chave manteria o valor antigo numa edicao — o backend mescla
      // o delta sobre o registro atual. Apagar um campo ficaria impossivel.
      expect(enviados[0]!.data).toEqual({ cliente: "Empresa A", obs: null });
    });

    it("converte numero e aceita virgula decimal", async () => {
      const enviados = capturarPost();
      montar([coluna({ key: "valor", name: "Valor", type: "number" })]);
      const usuario = digitador();

      await usuario.type(screen.getByLabelText("Valor"), "1234.5");
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      await waitFor(() => expect(enviados).toHaveLength(1));
      expect(enviados[0]!.data).toEqual({ valor: 1234.5 });
    });

    it("envia booleano como true/false, nunca como texto", async () => {
      const enviados = capturarPost();
      montar([coluna({ key: "ativo", name: "Ativo", type: "boolean" })]);
      const usuario = digitador();

      await usuario.click(screen.getByLabelText("Ativo"));
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      await waitFor(() => expect(enviados).toHaveLength(1));
      expect(enviados[0]!.data).toEqual({ ativo: true });
    });

    it("apara espacos das pontas", async () => {
      const enviados = capturarPost();
      montar([coluna()]);
      const usuario = digitador();

      await usuario.type(screen.getByLabelText("Cliente"), "  Empresa A  ");
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      await waitFor(() => expect(enviados).toHaveLength(1));
      expect(enviados[0]!.data).toEqual({ cliente: "Empresa A" });
    });
  });

  describe("erros", () => {
    it("mostra o erro da coluna no campo dela, mesmo aninhado sob `data`", async () => {
      servidor.use(
        http.post(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json(
            { data: { cliente: ["Este campo é obrigatório."] } },
            { status: 400 },
          ),
        ),
      );
      montar([coluna({ is_required: true })]);
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      // O `validate_data` devolve os erros ANINHADOS sob `data`, nao no nivel
      // de cima. Procurar `campo("cliente")` direto nao acharia nada e o
      // formulario seria recusado sem explicacao nenhuma na tela.
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Este campo é obrigatório.",
      );
    });

    it("mostra erro geral quando ele nao pertence a uma coluna", async () => {
      servidor.use(
        http.post(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json({ data: ["Chave desconhecida: fantasma."] }, { status: 400 }),
        ),
      );
      montar([coluna()]);
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Chave desconhecida: fantasma.",
      );
    });

    it("cai numa mensagem generica fora de validacao", async () => {
      servidor.use(
        http.post(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json({}, { status: 500 }),
        ),
      );
      montar([coluna()]);
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Não foi possível salvar o registro",
      );
    });
  });

  it("preenche os campos ao editar", () => {
    montar([coluna()], REGISTRO);

    expect(screen.getByRole("heading", { name: "Editar registro" })).toBeInTheDocument();
    expect(screen.getByLabelText("Cliente")).toHaveValue("Empresa A");
  });
});

function within_options(seletor: HTMLElement): string[] {
  return Array.from(seletor.querySelectorAll("option")).map((o) => o.textContent ?? "");
}
