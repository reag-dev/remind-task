import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Alerta } from "../api/tipos.ts";
import { API, servidor } from "../test/servidor.ts";
import { digitador, renderizar } from "../test/util.tsx";
import { Alertas } from "./Alertas.tsx";

function alerta(parcial: Partial<Alerta> = {}): Alerta {
  return {
    id: "a1",
    table_id: "t1",
    table_name: "Contratos",
    record_id: "r1",
    label: "Empresa A · CT-001",
    trigger_date: "2026-08-19",
    due_date: "2026-08-22",
    status: "sent",
    is_stale: false,
    notified_at: "2026-08-19T12:00:00Z",
    read_at: null,
    created_at: "2026-08-19T12:00:00Z",
    ...parcial,
  };
}

function inbox(...itens: Alerta[]) {
  return http.get(`${API}/alerts/`, () =>
    HttpResponse.json({
      count: itens.length,
      next: null,
      previous: null,
      results: itens,
    }),
  );
}

function montar(rota = "/alertas") {
  return renderizar(<Alertas />, { rota, caminho: "/alertas" });
}

describe("Alertas", () => {
  it("mostra rotulo, tabela e as duas datas", async () => {
    servidor.use(inbox(alerta()));
    montar();

    expect(await screen.findByText("Empresa A · CT-001")).toBeInTheDocument();
    // O `label` vem de `alerts.services.record_label`, que PULA colunas
    // sensiveis na origem — a inbox nunca monta o texto por conta propria.
    expect(screen.getByText(/Contratos/)).toBeInTheDocument();
    expect(screen.getByText(/22\/08\/2026/)).toBeInTheDocument();
    expect(screen.getByText(/19\/08\/2026/)).toBeInTheDocument();
  });

  it("filtra por `sent` por padrao, nao por `pending`", async () => {
    const vistas: URLSearchParams[] = [];
    servidor.use(
      http.get(`${API}/alerts/`, ({ request }) => {
        vistas.push(new URL(request.url).searchParams);
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );
    montar();

    // O job cria alertas `in_app` ja como `sent` (entrega no ato de gravar).
    // `pending` fica para canais que dependem de confirmacao de envio, e so
    // existe `in_app` hoje — filtrar por `pending` devolveria lista vazia
    // sempre, e pareceria "nao ha alertas".
    await waitFor(() => expect(vistas).toHaveLength(1));
    expect(vistas[0]!.get("status")).toBe("sent");
  });

  it("avisa quando o vencimento mudou depois do alerta", async () => {
    servidor.use(inbox(alerta({ is_stale: true })));
    montar();

    // Sem isto o usuario agiria sobre uma data que nao vale mais.
    expect(
      await screen.findByText(/vencimento foi alterado depois deste aviso/),
    ).toBeInTheDocument();
  });

  it("nao mostra o aviso de desatualizado quando a data bate", async () => {
    servidor.use(inbox(alerta({ is_stale: false })));
    montar();

    await screen.findByText("Empresa A · CT-001");
    expect(screen.queryByText(/vencimento foi alterado/)).not.toBeInTheDocument();
  });

  it("leva ao registro de origem", async () => {
    servidor.use(inbox(alerta({ table_id: "t9" })));
    montar();

    expect(
      await screen.findByRole("link", { name: "Empresa A · CT-001" }),
    ).toHaveAttribute("href", "/tabelas/t9");
  });

  describe("transicoes", () => {
    it("some da lista imediatamente ao marcar como lido", async () => {
      servidor.use(
        inbox(alerta()),
        http.post(`${API}/alerts/a1/read/`, async () => {
          // Latencia artificial: e o que revela se a atualizacao e otimista ou
          // se a tela espera o servidor.
          await new Promise((resolver) => setTimeout(resolver, 80));
          return HttpResponse.json(alerta({ status: "read" }));
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(
        await screen.findByRole("button", { name: "Marcar como lido" }),
      );

      // Sem esperar: a linha sai na hora. Esperar o servidor para riscar um
      // item de lista faz a inbox parecer travada.
      expect(screen.queryByText("Empresa A · CT-001")).not.toBeInTheDocument();
    });

    it("devolve o alerta a lista quando o servidor recusa", async () => {
      // O rollback só é observável numa JANELA: entre a falha da mutação e a
      // chegada do refetch que o `onSettled` dispara. Com o refetch instantâneo
      // o alerta volta de qualquer jeito, e o teste passaria sem rollback
      // nenhum — provando o refetch, não o que se quer provar. (Verificado por
      // sabotagem: sem este atraso, remover o rollback deixava tudo verde.)
      //
      // Daí o atraso na segunda listagem: dentro dessa janela, só o rollback
      // pode ter recolocado o item.
      let chamadas = 0;
      servidor.use(
        http.get(`${API}/alerts/`, async () => {
          chamadas += 1;
          if (chamadas > 1) await new Promise((resolver) => setTimeout(resolver, 3000));
          return HttpResponse.json({
            count: 1,
            next: null,
            previous: null,
            results: [alerta()],
          });
        }),
        http.post(`${API}/alerts/a1/read/`, () =>
          HttpResponse.json({ detail: "não" }, { status: 500 }),
        ),
      );
      montar();
      const usuario = digitador();

      await usuario.click(
        await screen.findByRole("button", { name: "Marcar como lido" }),
      );

      // Sem rollback o alerta sumiria da tela e continuaria pendente no banco —
      // o usuário acharia que tratou algo que não tratou.
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Não foi possível atualizar",
      );
      expect(screen.getByText("Empresa A · CT-001")).toBeInTheDocument();
      // O refetch ainda está em voo: o que se viu acima foi o rollback.
      expect(chamadas).toBe(2);
    });

    it("chama o endpoint de descarte", async () => {
      const descartou = vi.fn();
      servidor.use(
        inbox(alerta()),
        http.post(`${API}/alerts/a1/dismiss/`, () => {
          descartou();
          return HttpResponse.json(alerta({ status: "dismissed" }));
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Descartar" }));

      await waitFor(() => expect(descartou).toHaveBeenCalledTimes(1));
    });

    it("nao oferece 'marcar como lido' num alerta ja lido", async () => {
      servidor.use(inbox(alerta({ status: "read" })));
      montar("/alertas?status=read");

      await screen.findByText("Empresa A · CT-001");
      expect(
        screen.queryByRole("button", { name: "Marcar como lido" }),
      ).not.toBeInTheDocument();
    });

    it("nao oferece 'descartar' num alerta ja descartado", async () => {
      servidor.use(inbox(alerta({ status: "dismissed" })));
      montar("/alertas?status=dismissed");

      await screen.findByText("Empresa A · CT-001");
      expect(screen.queryByRole("button", { name: "Descartar" })).not.toBeInTheDocument();
    });
  });

  describe("abas", () => {
    it("troca o filtro e reinicia a paginacao", async () => {
      const vistas: URLSearchParams[] = [];
      servidor.use(
        http.get(`${API}/alerts/`, ({ request }) => {
          vistas.push(new URL(request.url).searchParams);
          return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
        }),
      );
      montar("/alertas?pagina=4");
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Lidos" }));

      await waitFor(() => {
        expect(vistas.at(-1)!.get("status")).toBe("read");
      });
      // A aba nova tem outra contagem; manter `pagina=4` pediria uma pagina
      // que pode nao existir e o backend responderia 404.
      expect(vistas.at(-1)!.get("page")).toBe("1");
    });

    it("'Todos' remove o filtro de status", async () => {
      const vistas: URLSearchParams[] = [];
      servidor.use(
        http.get(`${API}/alerts/`, ({ request }) => {
          vistas.push(new URL(request.url).searchParams);
          return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
        }),
      );
      montar();
      const usuario = digitador();

      await usuario.click(await screen.findByRole("button", { name: "Todos" }));

      await waitFor(() => expect(vistas.at(-1)!.has("status")).toBe(false));
    });
  });

  it("distingue inbox limpa de aba sem itens", async () => {
    servidor.use(inbox());
    montar();

    expect(
      await screen.findByText("Nenhum alerta esperando por você."),
    ).toBeInTheDocument();
  });

  it("conta as paginas pelo total do servidor", async () => {
    servidor.use(
      http.get(`${API}/alerts/`, () =>
        HttpResponse.json({
          count: 60,
          next: null,
          previous: null,
          results: [alerta()],
        }),
      ),
    );
    montar();

    // 60 alertas com 25 por pagina sao 3 paginas — mesma armadilha 8 da
    // listagem de registros, mesma defesa.
    const paginacao = await screen.findByRole("navigation", { name: "Paginação" });
    expect(within(paginacao).getByText("1 de 3")).toBeInTheDocument();
  });

  it("avisa quando a inbox nao carrega", async () => {
    servidor.use(
      http.get(`${API}/alerts/`, () => HttpResponse.json({}, { status: 500 })),
    );
    montar();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar os alertas",
    );
  });
});
