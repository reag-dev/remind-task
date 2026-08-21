/**
 * Armadilha 8 do plano, na superfície onde ela apareceria.
 *
 * O grid recebe UMA página. Se a contagem de páginas viesse do tamanho do array
 * em memória em vez do `count` do servidor, o rodapé diria "1 de 1" com 137
 * registros no banco — plausível, silencioso e errado.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { digitador } from "../test/util.tsx";
import { Paginacao } from "./Paginacao.tsx";

function montar(props: Partial<Parameters<typeof Paginacao>[0]> = {}) {
  const onPagina = vi.fn();
  const onTamanho = vi.fn();
  render(
    <Paginacao
      pagina={1}
      tamanho={50}
      total={137}
      nesta={50}
      onPagina={onPagina}
      onTamanho={onTamanho}
      {...props}
    />,
  );
  return { onPagina, onTamanho };
}

describe("Paginacao", () => {
  it("conta as paginas pelo total do servidor, nao pelas linhas na tela", () => {
    montar();

    // 137 registros, 50 por pagina = 3 paginas. Contar pelo array recebido
    // daria 1, que e exatamente o modo de falha da armadilha 8.
    expect(screen.getByText("1 de 3")).toBeInTheDocument();
    expect(screen.getByText("1–50 de 137 registros")).toBeInTheDocument();
  });

  it("calcula o intervalo correto nas paginas seguintes", () => {
    montar({ pagina: 3, nesta: 37 });

    expect(screen.getByText("101–137 de 137 registros")).toBeInTheDocument();
  });

  it("respeita o tamanho de pagina escolhido", () => {
    montar({ tamanho: 25, nesta: 25 });

    expect(screen.getByText("1 de 6")).toBeInTheDocument();
  });

  it("trava 'Anterior' na primeira e 'Proxima' na ultima", () => {
    montar({ pagina: 1 });
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Próxima" })).toBeEnabled();
  });

  it("trava 'Proxima' na ultima pagina", () => {
    montar({ pagina: 3, nesta: 37 });
    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
  });

  it("navega para frente e para tras", async () => {
    const { onPagina } = montar({ pagina: 2, nesta: 50 });
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "Próxima" }));
    expect(onPagina).toHaveBeenCalledWith(3);

    await usuario.click(screen.getByRole("button", { name: "Anterior" }));
    expect(onPagina).toHaveBeenCalledWith(1);
  });

  it("oferece so os tamanhos que o backend aceita", async () => {
    const { onTamanho } = montar();
    const usuario = digitador();

    const seletor = screen.getByLabelText("Por página");
    const opcoes = Array.from(seletor.querySelectorAll("option")).map((o) => o.value);
    // 200 e o `max_page_size` da PaginacaoPadrao. Oferecer mais faria o
    // servidor cortar em silencio e a contagem de paginas ficar errada.
    expect(opcoes).toEqual(["25", "50", "100", "200"]);

    await usuario.selectOptions(seletor, "100");
    expect(onTamanho).toHaveBeenCalledWith(100);
  });

  it("lida com lista vazia sem dividir por zero", () => {
    montar({ total: 0, nesta: 0 });

    expect(screen.getByText("Nenhum registro")).toBeInTheDocument();
    expect(screen.getByText("1 de 1")).toBeInTheDocument();
  });

  it("anuncia a troca de pagina para leitor de tela", () => {
    montar();

    // A troca de pagina muda a tabela inteira sem mover o foco: sem `aria-live`
    // quem usa leitor de tela nao tem como saber que algo mudou.
    expect(screen.getByText("1–50 de 137 registros")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });

  it("usa singular para um registro so", () => {
    montar({ total: 1, nesta: 1 });

    expect(screen.getByText("1–1 de 1 registro")).toBeInTheDocument();
  });
});
