import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Coluna, Registro } from "../api/tipos.ts";
import { API, servidor } from "../test/servidor.ts";
import { digitador, renderizar } from "../test/util.tsx";
import { TabelaRegistros } from "./TabelaRegistros.tsx";

const ID = "aaaaaaaa-0000-0000-0000-000000000001";

const COLUNA: Coluna = {
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
};

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

function cenario({
  colunas = [COLUNA],
  registros = [registro()],
  total,
}: {
  colunas?: Coluna[];
  registros?: Registro[];
  total?: number;
} = {}) {
  return [
    http.get(`${API}/tables/${ID}/`, () =>
      HttpResponse.json({
        id: ID,
        name: "Contratos",
        description: "",
        alert_lead_days: 3,
        columns: colunas,
        created_at: "2026-08-01T12:00:00Z",
        updated_at: "2026-08-01T12:00:00Z",
      }),
    ),
    http.get(`${API}/tables/${ID}/records/`, () =>
      HttpResponse.json({
        count: total ?? registros.length,
        next: null,
        previous: null,
        results: registros,
      }),
    ),
  ];
}

/**
 * Só o handler da tabela.
 *
 * Para os testes que precisam de uma lista de registros MUTÁVEL. Dentro de uma
 * mesma chamada de `servidor.use(...)` o primeiro handler que casa é o que
 * responde — espalhar `cenario()` antes de um handler próprio de `/records/`
 * faz o próprio ficar inalcançável, e a lista nunca muda.
 */
function soTabela(colunas: Coluna[] = [COLUNA]) {
  return http.get(`${API}/tables/${ID}/`, () =>
    HttpResponse.json({
      id: ID,
      name: "Contratos",
      description: "",
      alert_lead_days: 3,
      columns: colunas,
      created_at: "2026-08-01T12:00:00Z",
      updated_at: "2026-08-01T12:00:00Z",
    }),
  );
}

function montar() {
  return renderizar(<TabelaRegistros />, {
    rota: `/tabelas/${ID}`,
    caminho: "/tabelas/:id",
  });
}

describe("TabelaRegistros", () => {
  it("mostra o grid com os registros da tabela", async () => {
    servidor.use(...cenario());
    montar();

    expect(await screen.findByRole("heading", { name: "Contratos" })).toBeInTheDocument();
    expect(screen.getByText("Empresa A")).toBeInTheDocument();
  });

  it("manda configurar colunas antes de deixar inserir registro", async () => {
    servidor.use(...cenario({ colunas: [], registros: [] }));
    montar();

    // Sem coluna, o POST nao tem onde gravar valor. Oferecer "novo registro"
    // levaria a um formulario vazio que so pode dar erro.
    expect(await screen.findByText(/Defina as colunas antes/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Novo registro" }),
    ).not.toBeInTheDocument();
  });

  describe("paginacao, ordenacao e filtros", () => {
    /** Captura as query strings que chegaram a `/records/`. */
    function espiarConsultas() {
      const vistas: URLSearchParams[] = [];
      servidor.use(
        soTabela(),
        http.get(`${API}/tables/${ID}/records/`, ({ request }) => {
          vistas.push(new URL(request.url).searchParams);
          return HttpResponse.json({
            count: 137,
            next: null,
            previous: null,
            results: [registro()],
          });
        }),
      );
      return vistas;
    }

    it("conta as paginas pelo `count` do servidor — armadilha 8", async () => {
      espiarConsultas();
      montar();

      // 137 registros com 50 por pagina sao 3 paginas. Se a contagem viesse do
      // array recebido, o rodape diria "1 de 1" com 136 registros invisiveis.
      expect(await screen.findByText("1 de 3")).toBeInTheDocument();
      expect(screen.getByText("1–1 de 137 registros")).toBeInTheDocument();
    });

    it("sempre pede desempate na ordenacao — armadilha 9", async () => {
      const vistas = espiarConsultas();
      montar();
      await screen.findByText("Empresa A");

      // Sem `created_at` anexado, registros de mesmo vencimento ficam em ordem
      // indefinida e a mesma linha aparece em duas paginas ou em nenhuma.
      expect(vistas[0]!.get("ordering")).toBe("due_date,created_at");
    });

    it("envia page_size, que so existe por causa da PaginacaoPadrao", async () => {
      const vistas = espiarConsultas();
      montar();
      await screen.findByText("Empresa A");

      // O PageNumberPagination padrao do DRF ignoraria este parametro em
      // silencio. Ver core/pagination.py.
      expect(vistas[0]!.get("page_size")).toBe("50");
    });

    it("leva o filtro de status para o servidor", async () => {
      const vistas = espiarConsultas();
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Vencido" }));

      await waitFor(() => {
        expect(vistas.at(-1)!.get("status")).toBe("overdue");
      });
    });

    it("reseta a pagina ao filtrar", async () => {
      const vistas = espiarConsultas();
      renderizar(<TabelaRegistros />, {
        rota: `/tabelas/${ID}?pagina=3`,
        caminho: "/tabelas/:id",
      });
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Vencido" }));

      // Manter `page=3` num resultado filtrado menor daria 404, e a tela diria
      // "nao encontrado" para uma busca que tem resultados.
      await waitFor(() => {
        expect(vistas.at(-1)!.get("page")).toBe("1");
      });
    });

    it("inverte a direcao ao clicar no cabecalho de vencimento", async () => {
      const vistas = espiarConsultas();
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: /Status/ }));

      await waitFor(() => {
        expect(vistas.at(-1)!.get("ordering")).toBe("-due_date,created_at");
      });
    });

    it("nao oferece ordenacao em coluna dinamica do JSONB", async () => {
      espiarConsultas();
      montar();
      await screen.findByText("Empresa A");

      // O backend so ordena pelos `ordering_fields`. Um cabecalho clicavel em
      // "Cliente" geraria `?ordering=cliente`, que o servidor ignora — a tabela
      // nao mudaria e pareceria bug.
      const cabecalhos = screen.getAllByRole("columnheader");
      const cliente = cabecalhos.find((th) => th.textContent?.includes("Cliente"));
      expect(within(cliente!).queryByRole("button")).not.toBeInTheDocument();
    });

    it("anuncia a ordenacao ativa com aria-sort", async () => {
      espiarConsultas();
      montar();
      await screen.findByText("Empresa A");

      const status = screen
        .getAllByRole("columnheader")
        .find((th) => th.textContent?.includes("Status"));
      expect(status).toHaveAttribute("aria-sort", "ascending");
    });

    it("oferece voltar para a primeira pagina quando a atual sumiu", async () => {
      servidor.use(
        soTabela(),
        http.get(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json({ detail: "Página inválida." }, { status: 404 }),
        ),
      );
      renderizar(<TabelaRegistros />, {
        rota: `/tabelas/${ID}?pagina=9`,
        caminho: "/tabelas/:id",
      });

      // Pagina fora do intervalo responde 404 igual a tabela inexistente. Tratar
      // os dois igual jogaria o usuario para fora da tela por ter clicado em
      // "proxima" uma vez a mais.
      const aviso = await screen.findByRole("alert");
      expect(aviso).toHaveTextContent("Esta página não tem registros");
      expect(aviso).not.toHaveTextContent("Tabela não encontrada");
    });

    it("distingue lista vazia por filtro de tabela vazia", async () => {
      servidor.use(
        soTabela(),
        http.get(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
        ),
      );
      renderizar(<TabelaRegistros />, {
        rota: `/tabelas/${ID}?status=overdue`,
        caminho: "/tabelas/:id",
      });

      // "Nao ha nada" pede criar o primeiro registro; "nada casou" pede
      // afrouxar o filtro. A mesma frase manda o usuario para a acao errada.
      expect(
        await screen.findByText(/corresponde aos filtros aplicados/),
      ).toBeInTheDocument();
    });
  });

  it("trata tabela alheia como nao encontrada, sem falar em permissao", async () => {
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () => HttpResponse.json({}, { status: 404 })),
      http.get(`${API}/tables/${ID}/records/`, () =>
        HttpResponse.json({}, { status: 404 }),
      ),
    );
    montar();

    // RS04: 404 vale para inexistente E para tabela de outro dono, porque 403
    // confirmaria a existencia. Dizer "sem permissao" aqui reintroduziria na
    // tela o vazamento que tests/security/test_cross_tenant.py impede.
    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Tabela não encontrada.");
    expect(aviso.textContent).not.toMatch(/permiss|autoriza|acesso negado/i);
  });

  it("distingue falha de servidor de tabela inexistente", async () => {
    servidor.use(
      http.get(`${API}/tables/${ID}/`, () => HttpResponse.json({}, { status: 500 })),
      http.get(`${API}/tables/${ID}/records/`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    montar();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a tabela.",
    );
  });

  describe("inserir e editar", () => {
    it("abre o formulario vazio em 'novo registro'", async () => {
      servidor.use(...cenario());
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Novo registro" }));

      expect(screen.getByRole("heading", { name: "Novo registro" })).toBeInTheDocument();
      expect(screen.getByLabelText("Cliente")).toHaveValue("");
    });

    it("abre o formulario preenchido em 'editar'", async () => {
      servidor.use(...cenario());
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Editar" }));

      expect(
        screen.getByRole("heading", { name: "Editar registro" }),
      ).toBeInTheDocument();
      expect(screen.getByLabelText("Cliente")).toHaveValue("Empresa A");
    });

    it("recarrega a lista depois de inserir", async () => {
      let lista = [registro()];
      servidor.use(
        soTabela(),
        http.get(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json({
            count: lista.length,
            next: null,
            previous: null,
            results: lista,
          }),
        ),
        http.post(`${API}/tables/${ID}/records/`, () => {
          lista = [...lista, registro({ id: "r2", data: { cliente: "Empresa B" } })];
          return HttpResponse.json(lista[1], { status: 201 });
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Novo registro" }));
      await usuario.type(screen.getByLabelText("Cliente"), "Empresa B");
      await usuario.click(screen.getByRole("button", { name: "Salvar" }));

      // Sem a invalidacao da chave, o registro novo so apareceria com F5.
      expect(await screen.findByText("Empresa B")).toBeInTheDocument();
    });
  });

  describe("excluir", () => {
    it("nao chama a API ao cancelar", async () => {
      const excluiu = vi.fn();
      servidor.use(
        ...cenario(),
        http.delete(`${API}/tables/${ID}/records/:rid/`, () => {
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

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(excluiu).not.toHaveBeenCalled();
    });

    it("exclui e some da lista", async () => {
      let lista = [registro()];
      servidor.use(
        soTabela(),
        http.get(`${API}/tables/${ID}/records/`, () =>
          HttpResponse.json({
            count: lista.length,
            next: null,
            previous: null,
            results: lista,
          }),
        ),
        http.delete(`${API}/tables/${ID}/records/r1/`, () => {
          lista = [];
          return new HttpResponse(null, { status: 204 });
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Excluir" }));
      await usuario.click(
        within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir" }),
      );

      expect(
        await screen.findByText("Nenhum registro nesta tabela ainda."),
      ).toBeInTheDocument();
    });
  });
});
