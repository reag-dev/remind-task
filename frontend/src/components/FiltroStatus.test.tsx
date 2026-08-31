import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { digitador } from "../test/util.tsx";
import { FiltroStatus } from "./FiltroStatus.tsx";

function montar(props: Partial<Parameters<typeof FiltroStatus>[0]> = {}) {
  const onStatus = vi.fn();
  const onIntervalo = vi.fn();
  render(
    <FiltroStatus
      selecionados={[]}
      de={null}
      ate={null}
      onStatus={onStatus}
      onIntervalo={onIntervalo}
      {...props}
    />,
  );
  return { onStatus, onIntervalo };
}

describe("FiltroStatus", () => {
  it("começa recolhido quando não há filtro ativo", () => {
    montar();

    expect(screen.getByRole("button", { name: "Filtros" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Status" })).not.toBeInTheDocument();
  });

  it("expande ao clicar em Filtros e recolhe ao clicar em Ocultar", async () => {
    montar();
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "Filtros" }));
    expect(screen.getByRole("group", { name: "Status" })).toBeInTheDocument();

    await usuario.click(screen.getByRole("button", { name: "Ocultar" }));
    expect(screen.queryByRole("group", { name: "Status" })).not.toBeInTheDocument();
  });

  it("começa expandido quando já chega com filtro ativo (ex.: URL colada)", () => {
    montar({ selecionados: ["overdue"] });

    expect(screen.getByRole("group", { name: "Status" })).toBeInTheDocument();
  });

  it("mostra a contagem no botão recolhido quando esconde um filtro ativo", async () => {
    montar({ selecionados: ["overdue", "due_soon"] });
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "Ocultar" }));

    // 2 status selecionados; sem intervalo de datas ativo.
    expect(screen.getByRole("button", { name: "Filtros (2)" })).toBeInTheDocument();
  });

  it("conta o intervalo de datas como um filtro a mais na contagem", async () => {
    montar({ selecionados: ["overdue"], de: "2026-08-01", ate: null });
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "Ocultar" }));

    expect(screen.getByRole("button", { name: "Filtros (2)" })).toBeInTheDocument();
  });
});
