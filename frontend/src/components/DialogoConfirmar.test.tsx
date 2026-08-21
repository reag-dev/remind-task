import { fireEvent, render, screen } from "@testing-library/react";
import { digitador } from "../test/util.tsx";
import { describe, expect, it, vi } from "vitest";

import { DialogoConfirmar } from "./DialogoConfirmar.tsx";

function montar(props: Partial<Parameters<typeof DialogoConfirmar>[0]> = {}) {
  const onConfirmar = vi.fn();
  const onCancelar = vi.fn();
  render(
    <DialogoConfirmar
      titulo="Excluir coisa"
      rotuloConfirmar="Excluir"
      onConfirmar={onConfirmar}
      onCancelar={onCancelar}
      {...props}
    >
      <p>corpo</p>
    </DialogoConfirmar>,
  );
  return { onConfirmar, onCancelar };
}

describe("DialogoConfirmar", () => {
  it("abre como modal e mostra titulo e corpo", () => {
    montar();

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Excluir coisa" })).toBeInTheDocument();
    expect(screen.getByText("corpo")).toBeInTheDocument();
  });

  it("avisa o pai quando o Esc fecha o dialogo", () => {
    const { onCancelar } = montar();

    // `Esc` dispara `cancel` sem passar por botao nenhum. Sem tratar o evento,
    // o <dialog> fecharia no DOM enquanto o estado do React continuaria
    // achando que ele esta aberto — e ele nunca mais reabriria.
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));

    expect(onCancelar).toHaveBeenCalledTimes(1);
  });

  it("trava o botao de confirmar enquanto a acao esta em voo", () => {
    montar({ confirmando: true });

    // Sem isto, dois cliques disparam dois DELETE. O segundo responde 404 e a
    // tela mostraria um erro por uma exclusao que na verdade funcionou.
    expect(screen.getByRole("button", { name: "Excluindo…" })).toBeDisabled();
  });

  it("encaminha confirmar e cancelar", async () => {
    const { onConfirmar, onCancelar } = montar();
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "Excluir" }));
    expect(onConfirmar).toHaveBeenCalledTimes(1);

    await usuario.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancelar).toHaveBeenCalledTimes(1);
  });
});
