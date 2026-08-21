/**
 * Download do CSV (RF13).
 *
 * O jsdom não implementa `URL.createObjectURL`, `URL.revokeObjectURL` nem o
 * clique que inicia um download — nenhum deles existe fora de um browser de
 * verdade. Aqui eles são espionados, e o que se verifica é o que o CÓDIGO faz:
 * qual URL monta, quais headers manda, que nome dá ao arquivo e se libera o
 * blob. Que o browser realmente salve o arquivo é responsabilidade dele.
 */

import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { gravarAccessToken } from "../auth/sessao.ts";
import { API, servidor } from "../test/servidor.ts";
import { baixarCsv } from "./export.ts";

const ID = "aaaaaaaa-0000-0000-0000-000000000001";
const ROTA = `${API}/tables/${ID}/records/export/`;

let criados: string[] = [];
let liberados: string[] = [];
let cliques = 0;

beforeEach(() => {
  criados = [];
  liberados = [];
  cliques = 0;

  // Espiona os MÉTODOS ESTÁTICOS, sem trocar o global.
  // `vi.stubGlobal("URL", { ...URL, ... })` não funciona: espalhar uma classe
  // não copia o construtor, e todo `new URL(...)` do código sob teste passa a
  // estourar "URL is not a constructor" — inclusive o que monta a própria URL
  // da exportação.
  //
  // O jsdom não define `createObjectURL`/`revokeObjectURL`, então não há o que
  // espionar antes de criá-los.
  // O `??=` só atribui quando o método falta. A regra `unbound-method` o lê
  // como se fôssemos destacar o método do objeto para chamá-lo solto depois —
  // não é o caso, e o `in` como alternativa estreita `URL` para `never`, porque
  // a lib do TS jura que os métodos existem. Exceção pontual, duas linhas.
  /* eslint-disable @typescript-eslint/unbound-method */
  URL.createObjectURL ??= () => "";
  URL.revokeObjectURL ??= () => undefined;
  /* eslint-enable @typescript-eslint/unbound-method */

  vi.spyOn(URL, "createObjectURL").mockImplementation(() => {
    const endereco = `blob:fake/${criados.length}`;
    criados.push(endereco);
    return endereco;
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation((endereco: string) => {
    liberados.push(endereco);
  });

  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
    cliques += 1;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Responde um CSV e devolve as requisições vistas. */
function servirCsv(cabecalho?: string) {
  const vistas: Request[] = [];
  servidor.use(
    http.get(ROTA, ({ request }) => {
      vistas.push(request);
      return new HttpResponse("cliente,contrato\nEmpresa A,CT-001\n", {
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
          ...(cabecalho ? { "Content-Disposition": cabecalho } : {}),
        },
      });
    }),
  );
  return vistas;
}

describe("baixarCsv", () => {
  it("manda o token no header, e nunca na query string", async () => {
    gravarAccessToken("tok-123");
    const vistas = servirCsv();

    await baixarCsv(ID, {}, ",");

    expect(vistas[0]!.headers.get("Authorization")).toBe("Bearer tok-123");
    // Token na URL entra no log do servidor, no historico do browser e no
    // `Referer` de qualquer link que a pagina abra. E por isso que o download
    // nao pode ser um `<a href>`.
    expect(new URL(vistas[0]!.url).searchParams.has("token")).toBe(false);
    expect(vistas[0]!.url).not.toContain("tok-123");
  });

  it("usa o nome do arquivo que o servidor escolheu", async () => {
    gravarAccessToken("tok");
    servirCsv('attachment; filename="contratos-2026-08-20.csv"');

    const nomes: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      nomes.push(this.download);
    });

    await baixarCsv(ID, {}, ",");

    // So legivel porque o backend declara CORS_EXPOSE_HEADERS; sem isso o
    // browser esconde o header e `headers.get` devolve null sem avisar.
    expect(nomes).toEqual(["contratos-2026-08-20.csv"]);
  });

  it("cai num nome generico quando o header nao esta visivel", async () => {
    gravarAccessToken("tok");
    servirCsv(); // sem Content-Disposition, como numa resposta sem CORS_EXPOSE_HEADERS

    const nomes: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      nomes.push(this.download);
    });

    await baixarCsv(ID, {}, ",");

    // Degrada em vez de quebrar — mas o nome pior e o sintoma que o tripwire
    // do backend (test_export_authorization.py) existe para impedir.
    expect(nomes).toEqual(["registros.csv"]);
  });

  it("libera o blob depois do clique", async () => {
    gravarAccessToken("tok");
    servirCsv();

    await baixarCsv(ID, {}, ",");

    expect(cliques).toBe(1);
    // Sem o revoke o blob fica na memoria da aba ate ela fechar. Numa sessao
    // que exporta varias tabelas grandes isso vaza de verdade.
    expect(liberados).toEqual(criados);
  });

  it("leva os filtros da tela, sem page nem page_size", async () => {
    gravarAccessToken("tok");
    const vistas = servirCsv();

    await baixarCsv(
      ID,
      { ordering: "-due_date,created_at", status: "overdue", due_before: "2026-12-31" },
      ";",
    );

    const params = new URL(vistas[0]!.url).searchParams;
    // RS08: o export reusa a queryset da listagem. Ignorar o filtro visivel
    // seria mentira de UI — filtrar vencidos e receber a tabela inteira.
    expect(params.get("ordering")).toBe("-due_date,created_at");
    expect(params.get("status")).toBe("overdue");
    expect(params.get("due_before")).toBe("2026-12-31");
    expect(params.get("delimiter")).toBe(";");
    // O export transmite tudo, em streaming. Mandar `page` escreveria uma
    // intencao que o servidor ignora.
    expect(params.has("page")).toBe(false);
    expect(params.has("page_size")).toBe(false);
  });

  it("omite filtro vazio em vez de mandar parametro em branco", async () => {
    gravarAccessToken("tok");
    const vistas = servirCsv();

    await baixarCsv(ID, { ordering: "due_date,created_at", status: "" }, ",");

    expect(new URL(vistas[0]!.url).searchParams.has("status")).toBe(false);
  });

  it("renova o token e repete quando a sessao expirou no meio", async () => {
    gravarAccessToken("velho");
    let tentativas = 0;
    servidor.use(
      http.post(`${API}/auth/refresh/`, () => HttpResponse.json({ access: "novo" })),
      http.get(ROTA, ({ request }) => {
        tentativas += 1;
        if (request.headers.get("Authorization") !== "Bearer novo") {
          return HttpResponse.json({ detail: "expirado" }, { status: 401 });
        }
        return new HttpResponse("ok\n");
      }),
    );

    const { registrarRenovacao } = await import("./client.ts");
    const { renovarAccessToken } = await import("../auth/refresh.ts");
    registrarRenovacao(async () => {
      const token = await renovarAccessToken();
      if (!token) return false;
      gravarAccessToken(token);
      return true;
    });

    await baixarCsv(ID, {}, ",");

    // O access token dura 15 minutos. Sem reaproveitar o interceptor, exportar
    // depois de um tempo parado daria erro em vez de renovar.
    expect(tentativas).toBe(2);
    expect(cliques).toBe(1);
  });

  it("lanca sem baixar nada quando o servidor recusa", async () => {
    gravarAccessToken("tok");
    servidor.use(
      http.get(ROTA, () => HttpResponse.json({ detail: "não" }, { status: 404 })),
    );

    await expect(baixarCsv(ID, {}, ",")).rejects.toMatchObject({ status: 404 });
    // Nada de arquivo vazio salvo com nome bonito.
    expect(cliques).toBe(0);
    expect(criados).toEqual([]);
  });
});
