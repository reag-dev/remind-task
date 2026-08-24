import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

/**
 * Estado de paginação, ordenação e filtro — na URL, não no componente.
 *
 * Três razões para a URL ser a fonte da verdade, e não `useState`:
 *
 * 1. F5 preserva a visão. Quem estava olhando os vencidos da página 3 continua
 *    ali depois de recarregar.
 * 2. O link é compartilhável. "Olha esses contratos vencidos" vira uma URL.
 * 3. O botão "voltar" do browser passa a desfazer filtro em vez de sair da
 *    tela — que é o que o usuário espera dele.
 *
 * O preço é ter que serializar tudo para string, o que este hook concentra num
 * lugar só.
 */

export const TAMANHOS_DE_PAGINA = [25, 50, 100, 200] as const;

/**
 * Campos que o backend aceita em `?ordering=`.
 *
 * Espelha `RecordViewSet.ordering_fields`. As colunas dinâmicas do JSONB **não**
 * estão aqui: o backend não sabe ordenar por elas, e oferecer o clique no
 * cabeçalho produziria uma requisição que ele ignora — a tabela não mudaria e
 * pareceria um bug.
 */
export const CAMPOS_ORDENAVEIS = [
  "due_date",
  "created_at",
  "updated_at",
  "position",
] as const;

export type CampoOrdenavel = (typeof CAMPOS_ORDENAVEIS)[number];

/**
 * Desempate obrigatório em toda ordenação.
 *
 * O `NullsLastOrderingFilter` faz `order_by(*ordering)` com exatamente o que
 * veio na query string, **substituindo** o default `["due_date", "created_at"]`
 * do ViewSet. Então `?ordering=due_date` sozinho deixa registros de mesmo
 * vencimento em ordem indefinida entre uma requisição e outra — e a mesma linha
 * pode aparecer em duas páginas ou em nenhuma.
 *
 * Anexar `created_at` custa nada e torna o corte estável. Ele já está em
 * `ordering_fields`, então o backend aceita.
 */
const DESEMPATE: CampoOrdenavel = "created_at";

export type Ordenacao = { campo: CampoOrdenavel; descendente: boolean };

export type EstadoDaTabela = {
  pagina: number;
  tamanho: number;
  ordenacao: Ordenacao;
  /** Termo de busca; string vazia = sem busca. */
  busca: string;
  /** Status selecionados; vazio = sem filtro. */
  status: string[];
  vencendoAntesDe: string | null;
  vencendoDepoisDe: string | null;
};

const PADRAO: Ordenacao = { campo: "due_date", descendente: false };

export type ConsultaDaApi = {
  page: number;
  page_size: number;
  ordering: string;
  q?: string;
  status?: string;
  due_before?: string;
  due_after?: string;
};

export function paraOrdering({ campo, descendente }: Ordenacao): string {
  const principal = descendente ? `-${campo}` : campo;
  // Sem duplicar o desempate quando ele já é o campo principal: `?ordering=
  // created_at,created_at` é inofensivo mas confunde quem lê a URL.
  return campo === DESEMPATE ? principal : `${principal},${DESEMPATE}`;
}

export function useTabelaServidor() {
  const [params, setParams] = useSearchParams();

  const estado = useMemo<EstadoDaTabela>(() => {
    const campoBruto = params.get("ordenar") ?? PADRAO.campo;
    const campo = (CAMPOS_ORDENAVEIS as readonly string[]).includes(campoBruto)
      ? (campoBruto as CampoOrdenavel)
      : PADRAO.campo;

    const tamanhoBruto = Number(params.get("tamanho"));
    const tamanho = (TAMANHOS_DE_PAGINA as readonly number[]).includes(tamanhoBruto)
      ? tamanhoBruto
      : 50;

    const pagina = Number(params.get("pagina"));

    return {
      // A URL é editável por qualquer um. `?pagina=abc` vira NaN, e um NaN
      // chegando ao backend responde 404 — o usuário veria "não encontrado"
      // por um caractere digitado errado.
      pagina: Number.isInteger(pagina) && pagina > 0 ? pagina : 1,
      tamanho,
      ordenacao: { campo, descendente: params.get("desc") === "1" },
      busca: params.get("busca") ?? "",
      status: (params.get("status") ?? "").split(",").filter(Boolean),
      vencendoAntesDe: params.get("ate"),
      vencendoDepoisDe: params.get("de"),
    };
  }, [params]);

  /**
   * Aplica uma mudança e **volta para a página 1**.
   *
   * A regressão mais provável desta tela: mudar o filtro mantendo `pagina=7`
   * deixa o usuário numa página que não existe mais no resultado novo. O
   * backend responde 404, e a tela mostra "não encontrado" para uma busca que
   * na verdade tem resultados.
   *
   * Por isso o reset mora aqui dentro, e não em cada chamador — quem esquecer
   * de resetar não tem como esquecer, porque não existe caminho sem reset.
   */
  const alterar = useCallback(
    (mudancas: Partial<EstadoDaTabela>) => {
      setParams(
        (atuais) => {
          const proximos = new URLSearchParams(atuais);
          const definir = (chave: string, valor: string | null) => {
            if (valor === null || valor === "") proximos.delete(chave);
            else proximos.set(chave, valor);
          };

          if (mudancas.ordenacao) {
            definir("ordenar", mudancas.ordenacao.campo);
            definir("desc", mudancas.ordenacao.descendente ? "1" : null);
          }
          // `!== undefined`, e não um teste de veracidade: limpar a busca
          // manda `""`, que é falso — um `if (mudancas.busca)` engoliria o
          // pedido e o termo ficaria preso na URL depois de apagado do campo.
          if (mudancas.busca !== undefined) definir("busca", mudancas.busca);
          if (mudancas.status) definir("status", mudancas.status.join(","));
          if (mudancas.vencendoAntesDe !== undefined) {
            definir("ate", mudancas.vencendoAntesDe);
          }
          if (mudancas.vencendoDepoisDe !== undefined) {
            definir("de", mudancas.vencendoDepoisDe);
          }
          if (mudancas.tamanho) definir("tamanho", String(mudancas.tamanho));

          if (mudancas.pagina !== undefined) {
            definir("pagina", mudancas.pagina > 1 ? String(mudancas.pagina) : null);
          } else {
            // Qualquer coisa que não seja navegação de página reinicia a
            // paginação.
            proximos.delete("pagina");
          }

          return proximos;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  /** Alterna a direção quando o campo já está ativo; entra ascendente quando não. */
  const ordenarPor = useCallback(
    (campo: CampoOrdenavel) => {
      alterar({
        ordenacao: {
          campo,
          descendente: estado.ordenacao.campo === campo && !estado.ordenacao.descendente,
        },
      });
    },
    [alterar, estado.ordenacao],
  );

  const consulta = useMemo<ConsultaDaApi>(
    () => ({
      page: estado.pagina,
      page_size: estado.tamanho,
      ordering: paraOrdering(estado.ordenacao),
      ...(estado.busca ? { q: estado.busca } : {}),
      ...(estado.status.length > 0 ? { status: estado.status.join(",") } : {}),
      ...(estado.vencendoAntesDe ? { due_before: estado.vencendoAntesDe } : {}),
      ...(estado.vencendoDepoisDe ? { due_after: estado.vencendoDepoisDe } : {}),
    }),
    [estado],
  );

  /**
   * A mesma consulta, sem paginação — para a exportação (RF13).
   *
   * Derivada de `consulta` em vez de montada em paralelo: são as duas metades
   * da mesma promessa do RS08 (o export usa a queryset da listagem), e duas
   * construções independentes divergiriam no dia em que um filtro novo entrasse
   * só numa delas.
   *
   * `page` e `page_size` saem porque o export transmite a queryset inteira, em
   * streaming, sem paginar. Enviá-los escreveria na URL uma intenção que o
   * servidor ignora.
   */
  const filtrosDeExportacao = useMemo(() => {
    // Reconstruído a partir de `consulta`, e não por desestruturação com
    // descarte: `const { page, page_size, ...resto }` deixa duas variáveis sem
    // uso que o lint reprova, e silenciá-las com `_` esconderia que a lista
    // precisa ser revisada quando um filtro novo entrar.
    const { ordering, q, status, due_before, due_after } = consulta;
    return { ordering, q, status, due_before, due_after };
  }, [consulta]);

  return { estado, consulta, filtrosDeExportacao, alterar, ordenarPor };
}
