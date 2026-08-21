import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { gravarAccessToken } from "../auth/sessao.ts";
import { API, servidor } from "../test/servidor.ts";
import { digitador } from "../test/util.tsx";
import { BotaoExportar } from "./BotaoExportar.tsx";

const ID = "aaaaaaaa-0000-0000-0000-000000000001";
const ROTA = `${API}/tables/${ID}/records/export/`;

beforeEach(() => {
  gravarAccessToken("tok");
  // Ver o comentário em `export.test.ts`: o jsdom não tem estes métodos, e
  // trocar o global `URL` inteiro quebraria `new URL(...)`.
  /* eslint-disable @typescript-eslint/unbound-method -- ver `export.test.ts` */
  URL.createObjectURL ??= () => "";
  URL.revokeObjectURL ??= () => undefined;
  /* eslint-enable @typescript-eslint/unbound-method */
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

function montar(total = 3) {
  render(
    <BotaoExportar
      tabelaId={ID}
      filtros={{ ordering: "due_date,created_at", status: "overdue" }}
      total={total}
    />,
  );
}

describe("BotaoExportar", () => {
  it("diz quantas linhas vão sair", () => {
    montar(42);

    // O botão anuncia o resultado do filtro atual, não "exportar tabela": são
    // coisas diferentes assim que existe um filtro ativo.
    expect(
      screen.getByRole("button", { name: "Exportar 42 em CSV" }),
    ).toBeInTheDocument();
  });

  it("não deixa exportar uma lista vazia", () => {
    montar(0);

    // Um CSV só com cabeçalho não ajuda ninguém, e o clique parece ter falhado.
    expect(screen.getByRole("button", { name: /Exportar/ })).toBeDisabled();
  });

  it("leva os filtros da tela para a requisição", async () => {
    const vistas: Request[] = [];
    servidor.use(
      http.get(ROTA, ({ request }) => {
        vistas.push(request);
        return new HttpResponse("a,b\n");
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: /Exportar/ }));

    await waitFor(() => expect(vistas).toHaveLength(1));
    const params = new URL(vistas[0]!.url).searchParams;
    // É o que a docstring de `RecordViewSet.export` promete (RS08). Exportar
    // ignorando o filtro visível seria mentira de UI.
    expect(params.get("status")).toBe("overdue");
    expect(params.get("ordering")).toBe("due_date,created_at");
  });

  it("oferece ponto e vírgula para o Excel em pt-BR", async () => {
    const vistas: Request[] = [];
    servidor.use(
      http.get(ROTA, ({ request }) => {
        vistas.push(request);
        return new HttpResponse("a;b\n");
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.selectOptions(screen.getByLabelText("Separador"), ";");
    await usuario.click(screen.getByRole("button", { name: /Exportar/ }));

    await waitFor(() => expect(vistas).toHaveLength(1));
    expect(new URL(vistas[0]!.url).searchParams.get("delimiter")).toBe(";");
  });

  it("mostra que está gerando enquanto o arquivo não chega", async () => {
    servidor.use(
      http.get(ROTA, async () => {
        await new Promise((resolver) => setTimeout(resolver, 100));
        return new HttpResponse("a,b\n");
      }),
    );
    montar();
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: /Exportar/ }));

    // A resposta é streaming e pode demorar. Sem o estado de espera o usuário
    // clicaria de novo achando que falhou — e baixaria o arquivo duas vezes.
    expect(await screen.findByRole("button", { name: "Gerando…" })).toBeDisabled();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Exportar/ })).toBeEnabled(),
    );
  });

  it("avisa quando o servidor recusa", async () => {
    servidor.use(http.get(ROTA, () => HttpResponse.json({}, { status: 500 })));
    montar();
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: /Exportar/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível gerar o arquivo",
    );
  });
});
