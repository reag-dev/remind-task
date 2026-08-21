import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, servidor } from "../test/servidor.ts";
import { renderizar } from "../test/util.tsx";
import { BadgeAlertas } from "./BadgeAlertas.tsx";

function comContagem(total: number) {
  const vistas: URLSearchParams[] = [];
  servidor.use(
    http.get(`${API}/alerts/`, ({ request }) => {
      vistas.push(new URL(request.url).searchParams);
      return HttpResponse.json({
        count: total,
        next: null,
        previous: null,
        // Uma linha só, mesmo com contagem alta: é o que o `page_size=1` pede.
        results: total > 0 ? [{ id: "a1" }] : [],
      });
    }),
  );
  return vistas;
}

describe("BadgeAlertas", () => {
  it("pede uma linha só, porque só a contagem interessa", async () => {
    const vistas = comContagem(7);
    renderizar(<BadgeAlertas />);

    await waitFor(() => expect(vistas).toHaveLength(1));
    // Só é possível por causa da PaginacaoPadrao da Phase 5. Com o padrão do
    // DRF, cada atualização do contador baixaria a primeira página inteira.
    expect(vistas[0]!.get("page_size")).toBe("1");
    expect(vistas[0]!.get("status")).toBe("sent");
  });

  it("mostra a contagem de não lidos", async () => {
    comContagem(7);
    renderizar(<BadgeAlertas />);

    expect(await screen.findByText("7")).toBeInTheDocument();
  });

  it("não mostra bolinha quando a inbox está limpa", async () => {
    comContagem(0);
    renderizar(<BadgeAlertas />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /Alertas/ })).toBeInTheDocument();
    });
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("corta em 99+ para não estourar o cabeçalho", async () => {
    comContagem(1204);
    renderizar(<BadgeAlertas />);

    expect(await screen.findByText("99+")).toBeInTheDocument();
  });

  it("põe a contagem no texto acessível, não só na cor", async () => {
    comContagem(3);
    renderizar(<BadgeAlertas />);

    // Sem `aria-label`, quem usa leitor de tela ouviria apenas "Alertas" e não
    // saberia que há três coisas esperando.
    expect(await screen.findByLabelText("3 não lidos")).toBeInTheDocument();
  });

  it("usa singular para um alerta só", async () => {
    comContagem(1);
    renderizar(<BadgeAlertas />);

    expect(await screen.findByLabelText("1 não lido")).toBeInTheDocument();
  });
});
