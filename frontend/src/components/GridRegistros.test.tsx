import { render, screen, within } from "@testing-library/react";
import { digitador } from "../test/util.tsx";
import { describe, expect, it, vi } from "vitest";

import type { Coluna, Registro } from "../api/tipos.ts";
import { DUE_STATUS } from "../api/tipos.ts";
import { GridRegistros } from "./GridRegistros.tsx";

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

function registro(parcial: Partial<Registro> = {}): Registro {
  return {
    id: "r1",
    data: { cliente: "Empresa A" },
    due_date: "2026-08-22",
    due_status: "due_soon",
    days_until_due: 2,
    position: null,
    created_at: "2026-08-01T12:00:00Z",
    updated_at: "2026-08-01T12:00:00Z",
    ...parcial,
  };
}

function montar(colunas: Coluna[], registros: Registro[]) {
  return render(
    <GridRegistros
      colunas={colunas}
      registros={registros}
      comFiltro={false}
      ordenacao={{ campo: "due_date", descendente: false }}
      onOrdenar={vi.fn()}
      onEditar={vi.fn()}
      onExcluir={vi.fn()}
    />,
  );
}

describe("GridRegistros", () => {
  it("usa `key` da coluna para ler o JSONB, nao `name`", () => {
    // O `name` e rotulo e muda quando o usuario renomeia a coluna; a `key` e o
    // slug imutavel que indexa o JSONB. Trocar os dois faria a celula ficar
    // vazia justamente depois de um "renomear".
    montar(
      [coluna({ key: "cliente", name: "Nome do cliente" })],
      [registro({ data: { cliente: "Empresa A", "Nome do cliente": "ERRADO" } })],
    );

    expect(screen.getByText("Empresa A")).toBeInTheDocument();
    expect(screen.queryByText("ERRADO")).not.toBeInTheDocument();
  });

  it("respeita a ordem das colunas vinda do backend", () => {
    montar(
      [
        coluna({ id: "c1", key: "b", name: "Segunda", position: 0 }),
        coluna({ id: "c2", key: "a", name: "Primeira", position: 1 }),
      ],
      [registro({ data: { a: "x", b: "y" } })],
    );

    // As setas de ordenação (↑ ↓ ↕) entram no `textContent` do cabeçalho, então
    // são removidas antes de comparar — o teste é sobre ORDEM das colunas, não
    // sobre a afordância de ordenar, que tem testes próprios.
    const cabecalhos = screen
      .getAllByRole("columnheader")
      .map((th) => (th.textContent ?? "").replace(/[↑↓↕]/g, "").trim());
    // Status primeiro: a pergunta que traz alguem a esta tela e "o que esta
    // vencendo", e a resposta nao deve exigir rolagem ate a ultima coluna.
    expect(cabecalhos.slice(0, 3)).toEqual(["Status", "Segunda", "Primeira"]);
  });

  it("mostra vazio quando nao ha registros", () => {
    montar([coluna()], []);

    expect(screen.getByText(/Nenhum registro/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  describe("RF10 — indicadores de vencimento", () => {
    it.each(DUE_STATUS)("renderiza um selo distinto para %s", (status) => {
      montar([coluna()], [registro({ due_status: status, days_until_due: 0 })]);

      const selos = {
        overdue: "Vencido",
        due_today: "Vence hoje",
        due_soon: "Próximo do vencimento",
        on_track: "Em dia",
        no_due: "Sem vencimento",
      };
      expect(screen.getByText(selos[status], { exact: false })).toBeInTheDocument();
    });

    it("acompanha o selo de texto, nao so de cor", () => {
      montar([coluna()], [registro({ due_status: "overdue", days_until_due: -5 })]);

      // Cor sozinha nao e indicador: exclui quem tem daltonismo. A spec pede
      // "indicadores visuais", nao uma paleta.
      expect(screen.getByText("Vencido", { exact: false })).toBeInTheDocument();
      expect(screen.getByText(/há 5 dias/)).toBeInTheDocument();
    });

    it("mostra o valor cru se o backend inventar um status novo", () => {
      // `due_status` sai do schema como `string`, nao como uniao — a
      // compilacao nao protege. Melhor mostrar o desconhecido do que nada.
      montar([coluna()], [registro({ due_status: "reagendado", days_until_due: null })]);

      expect(screen.getByText("reagendado")).toBeInTheDocument();
    });
  });

  describe("RS05 — colunas sensiveis", () => {
    const colunaSensivel = coluna({ key: "cpf", name: "CPF", is_sensitive: true });
    const comCpf = registro({ data: { cpf: "111.222.333-44" } });

    it("nao coloca o valor no DOM antes de revelar", () => {
      montar([colunaSensivel], [comCpf]);

      // `queryByText` nao acha porque o texto nao esta renderizado. A checagem
      // no HTML inteiro fecha a brecha de estar presente porem escondido por
      // CSS — o que nao protegeria de nada.
      expect(screen.queryByText("111.222.333-44")).not.toBeInTheDocument();
      expect(document.body.innerHTML).not.toContain("111.222.333-44");
      expect(screen.getByRole("button", { name: "Revelar CPF" })).toBeInTheDocument();
    });

    it("revela e volta a esconder sob comando", async () => {
      montar([colunaSensivel], [comCpf]);
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "Revelar CPF" }));
      expect(screen.getByText("111.222.333-44")).toBeInTheDocument();

      await usuario.click(screen.getByRole("button", { name: "Ocultar CPF" }));
      expect(document.body.innerHTML).not.toContain("111.222.333-44");
    });

    it("nao mascara celula vazia", () => {
      montar([colunaSensivel], [registro({ data: {} })]);

      // Mascarar o vazio faria parecer que existe um valor guardado ali.
      expect(screen.queryByRole("button", { name: /Revelar/ })).not.toBeInTheDocument();
    });
  });

  describe("formatacao por tipo", () => {
    it("renderiza booleano, numero, data, e-mail e lista", () => {
      montar(
        [
          coluna({ id: "c1", key: "ativo", name: "Ativo", type: "boolean" }),
          coluna({ id: "c2", key: "valor", name: "Valor", type: "number" }),
          coluna({ id: "c3", key: "vence", name: "Vence", type: "due_date" }),
          coluna({ id: "c4", key: "email", name: "E-mail", type: "email" }),
          coluna({ id: "c5", key: "st", name: "Status", type: "select" }),
        ],
        [
          registro({
            data: {
              ativo: true,
              valor: 1234.5,
              vence: "2026-08-22",
              email: "a@b.test",
              st: "Ativo",
            },
          }),
        ],
      );

      expect(screen.getByLabelText("sim")).toBeInTheDocument();
      expect(screen.getByText("1.234,5")).toBeInTheDocument();
      expect(screen.getByText("22/08/2026")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "a@b.test" })).toHaveAttribute(
        "href",
        "mailto:a@b.test",
      );
    });

    it("marca celula sem valor com um traco", () => {
      montar([coluna()], [registro({ data: {} })]);

      const linha = screen.getAllByRole("row")[1];
      expect(within(linha!).getByText("—")).toBeInTheDocument();
    });
  });

  it("expoe editar e excluir por linha", async () => {
    const onEditar = vi.fn();
    const onExcluir = vi.fn();
    render(
      <GridRegistros
        colunas={[coluna()]}
        registros={[registro({ id: "r7" })]}
        comFiltro={false}
        ordenacao={{ campo: "due_date", descendente: false }}
        onOrdenar={vi.fn()}
        onEditar={onEditar}
        onExcluir={onExcluir}
      />,
    );
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "Editar" }));
    expect(onEditar).toHaveBeenCalledWith(expect.objectContaining({ id: "r7" }));

    await usuario.click(screen.getByRole("button", { name: "Excluir" }));
    expect(onExcluir).toHaveBeenCalledWith(expect.objectContaining({ id: "r7" }));
  });
});
