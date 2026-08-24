/**
 * Armadilhas 8, 9 e 10 do plano, no lugar onde elas moram.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { digitador } from "../test/util.tsx";
import { paraOrdering, useTabelaServidor } from "./useTabelaServidor.ts";

/** Expõe o estado e a consulta do hook como texto inspecionável. */
function Sonda() {
  const { estado, consulta, filtrosDeExportacao, alterar, ordenarPor } =
    useTabelaServidor();
  const local = useLocation();

  return (
    <div>
      <p data-testid="consulta">{JSON.stringify(consulta)}</p>
      <p data-testid="estado">{JSON.stringify(estado)}</p>
      <p data-testid="url">{local.search}</p>
      <p data-testid="exportacao">{JSON.stringify(filtrosDeExportacao)}</p>
      <button type="button" onClick={() => ordenarPor("due_date")}>
        ordenar vencimento
      </button>
      <button type="button" onClick={() => ordenarPor("created_at")}>
        ordenar criacao
      </button>
      <button type="button" onClick={() => alterar({ status: ["overdue"] })}>
        filtrar vencidos
      </button>
      <button type="button" onClick={() => alterar({ status: [] })}>
        limpar status
      </button>
      <button type="button" onClick={() => alterar({ busca: "aurora" })}>
        buscar aurora
      </button>
      <button type="button" onClick={() => alterar({ busca: "" })}>
        limpar busca
      </button>
      <button type="button" onClick={() => alterar({ pagina: 3 })}>
        ir para pagina 3
      </button>
      <button type="button" onClick={() => alterar({ tamanho: 100 })}>
        cem por pagina
      </button>
    </div>
  );
}

function montar(url = "/") {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/" element={<Sonda />} />
      </Routes>
    </MemoryRouter>,
  );
}

function consulta(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("consulta").textContent ?? "{}") as Record<
    string,
    unknown
  >;
}

function estado(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("estado").textContent ?? "{}") as Record<
    string,
    unknown
  >;
}

function exportacao(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("exportacao").textContent ?? "{}") as Record<
    string,
    unknown
  >;
}

describe("paraOrdering — armadilha 9", () => {
  it("anexa created_at como desempate", () => {
    // O NullsLastOrderingFilter faz `order_by(*ordering)` com exatamente o que
    // veio na URL, SUBSTITUINDO o default `["due_date", "created_at"]` do
    // ViewSet. Sem desempate, registros de mesmo vencimento ficam em ordem
    // indefinida entre requisicoes — e a mesma linha aparece em duas paginas
    // ou em nenhuma.
    expect(paraOrdering({ campo: "due_date", descendente: false })).toBe(
      "due_date,created_at",
    );
    expect(paraOrdering({ campo: "due_date", descendente: true })).toBe(
      "-due_date,created_at",
    );
  });

  it("nao duplica o desempate quando ele ja e o campo principal", () => {
    expect(paraOrdering({ campo: "created_at", descendente: true })).toBe("-created_at");
  });
});

describe("useTabelaServidor", () => {
  it("comeca na pagina 1, 50 por pagina, ordenado por vencimento", () => {
    montar();

    expect(consulta()).toEqual({
      page: 1,
      page_size: 50,
      ordering: "due_date,created_at",
    });
  });

  it("le o estado da URL, para F5 e link compartilhado preservarem a visao", () => {
    montar("/?pagina=3&tamanho=100&ordenar=updated_at&desc=1&status=overdue,due_today");

    expect(consulta()).toEqual({
      page: 3,
      page_size: 100,
      ordering: "-updated_at,created_at",
      status: "overdue,due_today",
    });
  });

  describe("valores invalidos na URL", () => {
    it.each([
      ["?pagina=abc", "pagina", 1],
      ["?pagina=-2", "pagina", 1],
      ["?pagina=0", "pagina", 1],
    ])("%s cai no padrao", (query, chave, esperado) => {
      // A URL e editavel por qualquer um. Um NaN chegando ao backend responde
      // 404, e o usuario veria "nao encontrado" por um caractere digitado errado.
      montar(`/${query}`);
      expect(estado()[chave]).toBe(esperado);
    });

    it("tamanho fora da lista permitida cai em 50", () => {
      // Nao basta confiar no teto do backend: um `?tamanho=999` faria o seletor
      // de linhas por pagina mostrar um valor que nao existe entre as opcoes.
      montar("/?tamanho=999");
      expect(estado().tamanho).toBe(50);
    });

    it("campo de ordenacao desconhecido cai em due_date", () => {
      // So os campos de `ordering_fields` do backend valem. `?ordenar=cliente`
      // geraria uma requisicao que o servidor ignora — a tabela nao mudaria e
      // pareceria bug.
      montar("/?ordenar=cliente");
      expect(consulta().ordering).toBe("due_date,created_at");
    });
  });

  describe("reset de pagina — a regressao mais provavel", () => {
    it("volta para a pagina 1 ao mudar o filtro", async () => {
      montar("/?pagina=7");
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "filtrar vencidos" }));

      // Manter `pagina=7` deixaria o usuario numa pagina que nao existe no
      // resultado novo: o backend responde 404 e a tela diria "nao encontrado"
      // para uma busca que na verdade tem resultados.
      expect(consulta().page).toBe(1);
      expect(consulta().status).toBe("overdue");
    });

    it("volta para a pagina 1 ao mudar a ordenacao", async () => {
      montar("/?pagina=7");
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "ordenar criacao" }));

      expect(consulta().page).toBe(1);
    });

    it("volta para a pagina 1 ao mudar o tamanho da pagina", async () => {
      montar("/?pagina=7");
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "cem por pagina" }));

      expect(consulta()).toMatchObject({ page: 1, page_size: 100 });
    });

    it("NAO reseta quando a mudanca e a propria navegacao de pagina", async () => {
      montar("/?status=overdue");
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "ir para pagina 3" }));

      expect(consulta()).toMatchObject({ page: 3, status: "overdue" });
    });
  });

  describe("alternancia de direcao", () => {
    it("clicar no campo ativo inverte a direcao", async () => {
      montar();
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "ordenar vencimento" }));
      expect(consulta().ordering).toBe("-due_date,created_at");

      await usuario.click(screen.getByRole("button", { name: "ordenar vencimento" }));
      expect(consulta().ordering).toBe("due_date,created_at");
    });

    it("clicar em outro campo entra ascendente, nao herda a direcao", async () => {
      montar("/?ordenar=due_date&desc=1");
      const usuario = digitador();

      await usuario.click(screen.getByRole("button", { name: "ordenar criacao" }));

      expect(consulta().ordering).toBe("created_at");
    });
  });

  it("mantem o estado na URL, e nao so na memoria", async () => {
    montar();
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "filtrar vencidos" }));

    // Sem isto, F5 perderia o filtro e o link nao seria compartilhavel.
    expect(screen.getByTestId("url").textContent).toContain("status=overdue");
  });

  it("mudar a ordenacao NAO descarta o filtro ativo", async () => {
    montar("/?status=overdue");
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "ordenar criacao" }));

    // Os eixos sao independentes: reordenar uma lista filtrada e uma acao
    // comum, e perder o filtro no caminho seria hostil.
    expect(consulta()).toMatchObject({ status: "overdue", ordering: "created_at" });
  });

  it("apaga o parametro da URL em vez de gravar valor vazio", async () => {
    montar("/?status=overdue");
    const usuario = digitador();

    await usuario.click(screen.getByRole("button", { name: "limpar status" }));

    // `?status=` vazio e ruido numa URL que se pretende compartilhavel; filtro
    // ausente e a AUSENCIA do parametro.
    expect(consulta()).not.toHaveProperty("status");
    expect(screen.getByTestId("url").textContent).not.toContain("status");
  });
});

describe("busca", () => {
  it("le o termo da URL — F5 e link compartilhado preservam a busca", () => {
    montar("/?busca=aurora");

    expect(estado()).toMatchObject({ busca: "aurora" });
    expect(consulta()).toMatchObject({ q: "aurora" });
  });

  it("sem termo, nao manda `q` — o backend nao recebe filtro vazio", () => {
    montar("/");

    expect(estado()).toMatchObject({ busca: "" });
    expect(consulta()).not.toHaveProperty("q");
  });

  it("buscar volta para a pagina 1", async () => {
    const usuario = digitador();
    montar("/?pagina=4");

    await usuario.click(screen.getByRole("button", { name: "buscar aurora" }));

    // Mesma armadilha dos demais filtros: manter `pagina=4` deixaria o usuario
    // numa pagina que o resultado novo pode nao ter, e o 404 do backend
    // apareceria como "nao encontrado" para uma busca que tem resultado.
    expect(estado()).toMatchObject({ pagina: 1, busca: "aurora" });
    expect(screen.getByTestId("url").textContent).not.toContain("pagina=4");
  });

  it("apagar o termo tira o parametro da URL, em vez de deixa-lo preso", async () => {
    const usuario = digitador();
    montar("/?busca=aurora");

    await usuario.click(screen.getByRole("button", { name: "limpar busca" }));

    // O `alterar` testa `!== undefined`, e nao veracidade: string vazia e
    // falsa, e um `if (mudancas.busca)` engoliria o pedido de limpeza — o
    // campo ficaria vazio na tela com a busca ainda ativa na URL.
    expect(screen.getByTestId("url").textContent).not.toContain("busca");
    expect(estado()).toMatchObject({ busca: "" });
  });

  it("buscar NAO descarta o filtro de status ativo", async () => {
    const usuario = digitador();
    montar("/?status=overdue");

    await usuario.click(screen.getByRole("button", { name: "buscar aurora" }));

    expect(consulta()).toMatchObject({ q: "aurora", status: "overdue" });
  });
});

describe("filtrosDeExportacao", () => {
  it("carrega os mesmos filtros da listagem, sem paginacao", () => {
    montar(
      "/?pagina=3&tamanho=100&status=overdue&ate=2026-12-31&ordenar=due_date&desc=1",
    );

    // RS08: o export reusa a queryset da listagem. Duas construcoes
    // independentes divergiriam no dia em que um filtro novo entrasse so numa.
    expect(exportacao()).toEqual({
      ordering: "-due_date,created_at",
      q: undefined,
      status: "overdue",
      due_before: "2026-12-31",
      due_after: undefined,
    });
  });

  it("leva a busca junto — o CSV sai igual a lista na tela", () => {
    montar("/?busca=aurora&status=overdue");

    // RS08 de novo, no filtro mais novo: quem ve 3 linhas na tela e exporta
    // esperando 3 linhas nao pode receber a tabela inteira.
    expect(exportacao()).toMatchObject({ q: "aurora", status: "overdue" });
  });

  it("nao leva page nem page_size", () => {
    montar("/?pagina=3&tamanho=100");

    // O export transmite a queryset inteira em streaming. Mandar `page`
    // escreveria na URL uma intencao que o servidor ignora — e daria a
    // impressao de que o arquivo respeita a pagina aberta.
    expect(exportacao()).not.toHaveProperty("page");
    expect(exportacao()).not.toHaveProperty("page_size");
  });
});
