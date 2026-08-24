/**
 * O que se testa aqui é o *debounce*, porque é onde esta tela pode ficar cara.
 *
 * Sem ele, cada tecla vira uma requisição: "aurora" são seis chamadas à API,
 * cinco delas descartadas — e cada uma varrendo colunas de texto com ILIKE, que
 * é justamente a consulta que o plano registrou como sem índice de apoio.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BarraBusca } from "./BarraBusca.tsx";

/**
 * `userEvent` precisa saber avançar os timers falsos.
 *
 * Sem `advanceTimers`, ele espera por temporizadores reais que o Vitest
 * congelou, e o teste estoura o timeout em vez de falhar com uma asserção —
 * um vermelho que não diz nada sobre o componente.
 */
function digitadorComTimersFalsos() {
  return userEvent.setup({ delay: null, advanceTimers: vi.advanceTimersByTime });
}

function montar(valor = "") {
  const onBuscar = vi.fn();
  const { rerender } = render(<BarraBusca valor={valor} onBuscar={onBuscar} />);
  const campo = screen.getByLabelText("Buscar");
  return { onBuscar, campo, rerender };
}

beforeEach(() => {
  // `shouldAdvanceTime`: o relógio falso anda sozinho junto com o real.
  //
  // Sem ele, o Testing Library trava. O `userEvent` e o `waitFor` agendam
  // trabalho com `setTimeout` internamente, e um relógio 100% congelado nunca
  // o executa — o teste estoura o timeout do Vitest em vez de falhar numa
  // asserção, que é um vermelho que não diz nada sobre o componente.
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("debounce", () => {
  it("não busca a cada tecla", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo } = montar();

    await usuario.type(campo, "aurora");

    expect(onBuscar).not.toHaveBeenCalled();
  });

  it("busca uma vez só, com o termo inteiro, depois da pausa", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo } = montar();

    await usuario.type(campo, "aurora");
    await vi.advanceTimersByTimeAsync(400);

    expect(onBuscar).toHaveBeenCalledTimes(1);
    expect(onBuscar).toHaveBeenCalledWith("aurora");
  });

  it("continuar digitando reinicia a espera", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo } = montar();

    await usuario.type(campo, "au");
    await vi.advanceTimersByTimeAsync(300);
    expect(onBuscar).not.toHaveBeenCalled();

    await usuario.type(campo, "rora");
    await vi.advanceTimersByTimeAsync(400);

    expect(onBuscar).toHaveBeenCalledTimes(1);
    expect(onBuscar).toHaveBeenCalledWith("aurora");
  });
});

describe("atalhos", () => {
  it("Enter busca na hora, sem esperar a pausa", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo } = montar();

    await usuario.type(campo, "aurora{Enter}");

    expect(onBuscar).toHaveBeenCalledWith("aurora");
  });

  it("Esc limpa o campo e a busca", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo } = montar("aurora");

    await usuario.type(campo, "{Escape}");

    expect(onBuscar).toHaveBeenCalledWith("");
    expect(campo).toHaveValue("");
  });
});

describe("a URL é a fonte da verdade", () => {
  it("abrir uma URL com busca preenchida não dispara requisição", async () => {
    const { onBuscar, campo } = montar("aurora");

    expect(campo).toHaveValue("aurora");

    await vi.advanceTimersByTimeAsync(1000);

    expect(onBuscar).not.toHaveBeenCalled();
  });

  it("mudança vinda de fora — voltar, limpar filtros — reflete no campo", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo, rerender } = montar("aurora");

    // O pai muda o termo (o usuário apertou "voltar", por exemplo).
    rerender(<BarraBusca valor="boreal" onBuscar={onBuscar} />);
    expect(campo).toHaveValue("boreal");

    // E o campo sincronizado não pode ecoar de volta uma busca nova: seria um
    // laço — a URL muda o campo, o campo pede outra mudança de URL.
    await vi.advanceTimersByTimeAsync(1000);
    expect(onBuscar).not.toHaveBeenCalled();

    // Continua editável depois da sincronização.
    await usuario.clear(campo);
    await usuario.type(campo, "central");
    await vi.advanceTimersByTimeAsync(400);
    expect(onBuscar).toHaveBeenCalledWith("central");
  });

  it("apagar o termo pede a busca vazia, em vez de deixá-lo preso na URL", async () => {
    const usuario = digitadorComTimersFalsos();
    const { onBuscar, campo } = montar("aurora");

    await usuario.clear(campo);
    await vi.advanceTimersByTimeAsync(400);

    expect(onBuscar).toHaveBeenCalledWith("");
  });
});
