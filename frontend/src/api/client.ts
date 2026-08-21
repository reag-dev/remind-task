/**
 * Cliente HTTP da API.
 *
 * `fetch` nativo, sem axios. O único motivo para uma biblioteca aqui seria o
 * interceptor de refresh — e ele é código nosso de qualquer forma (ver
 * `auth/refresh.ts`, Phase 1), porque a regra de single-flight é específica
 * deste backend.
 */

export const API_URL = import.meta.env.VITE_API_URL;

/**
 * Corpo de erro do DRF.
 *
 * Erro de validação vem como `{campo: ["mensagem"], ...}`; erro geral vem como
 * `{detail: "mensagem"}`. Os dois formatos convivem na mesma resposta 400.
 */
export type CorpoDeErro = {
  detail?: string;
  /**
   * Um campo pode carregar um OBJETO, não só mensagens.
   *
   * O `validate_data` de `RecordSerializer` devolve os erros das colunas
   * aninhados sob `data` — `{"data": {"cpf": ["Formato inválido."]}}` — porque
   * o JSONB tem estrutura própria. Um tipo que só admitisse `string | string[]`
   * obrigaria a um cast em todo lugar que lê esse caso.
   */
  [campo: string]: string | string[] | Record<string, string | string[]> | undefined;
};

export class ApiError extends Error {
  // Campos declarados em vez de parameter properties do construtor: estas são
  // sintaxe que o TypeScript *emite*, e o `erasableSyntaxOnly` do tsconfig as
  // proíbe. O Vite apaga os tipos, não os transforma — código que dependa de
  // emissão simplesmente some no build.
  readonly status: number;
  readonly corpo: CorpoDeErro;

  constructor(status: number, corpo: CorpoDeErro) {
    super(corpo.detail ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.corpo = corpo;
  }

  /**
   * Mensagens de um campo específico, para exibir junto ao input.
   *
   * O `RegisterSerializer` do backend devolve os erros de senha já mapeados em
   * `password` justamente para isto — ver o comentário dele sobre não deixar
   * cair em `non_field_errors`.
   */
  campo(nome: string): string[] {
    const valor = this.corpo[nome];
    if (valor === undefined) return [];
    if (Array.isArray(valor)) return valor;
    // Erro aninhado (ver `CorpoDeErro`): quem quer as mensagens por sub-chave
    // lê `corpo[nome]` direto. Aqui devolvemos vazio em vez de "[object
    // Object]" na tela.
    if (typeof valor === "object") return [];
    return [valor];
  }
}

/**
 * Fonte do access token.
 *
 * Injetada pelo `AuthProvider` na Phase 1 em vez de importada dele: o provider
 * depende do cliente para fazer login, e o cliente precisa do token do provider.
 * Um import nos dois sentidos seria ciclo.
 */
let lerToken: () => string | null = () => null;

export function registrarFonteDeToken(fonte: () => string | null): void {
  lerToken = fonte;
}

/**
 * Ponto de extensão do interceptor de refresh (Phase 1).
 *
 * Recebe a requisição que tomou 401 e devolve `true` se conseguiu renovar o
 * token — caso em que `request` repete a chamada uma única vez.
 */
let aoReceber401: () => Promise<boolean> = () => Promise.resolve(false);

export function registrarRenovacao(renovar: () => Promise<boolean>): void {
  aoReceber401 = renovar;
}

type Opcoes = {
  method?: string;
  body?: unknown;
  /** Pares já prontos; valores `undefined` são descartados. */
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
};

function montarUrl(caminho: string, query?: Opcoes["query"]): string {
  const url = new URL(API_URL + caminho);
  for (const [chave, valor] of Object.entries(query ?? {})) {
    if (valor !== undefined) url.searchParams.set(chave, String(valor));
  }
  return url.toString();
}

async function lerCorpo(resposta: Response): Promise<CorpoDeErro> {
  // 204 não tem corpo, e um erro de proxy pode vir em HTML. Nenhum dos dois
  // deve virar exceção de parsing por cima do erro que realmente aconteceu.
  const texto = await resposta.text();
  if (!texto) return {};
  try {
    return JSON.parse(texto) as CorpoDeErro;
  } catch {
    return { detail: texto.slice(0, 200) };
  }
}

async function enviar(caminho: string, opcoes: Opcoes): Promise<Response> {
  const token = lerToken();

  return fetch(montarUrl(caminho, opcoes.query), {
    method: opcoes.method ?? "GET",
    headers: {
      ...(opcoes.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: opcoes.body !== undefined ? JSON.stringify(opcoes.body) : undefined,
    signal: opcoes.signal,
    // Sempre, não só em /auth/. O cookie de refresh tem `path=/api/auth/`, então
    // o browser já o restringe às rotas de auth sozinho; incluir credenciais em
    // todas as chamadas evita a categoria de bug em que alguém acrescenta uma
    // rota de auth e esquece a flag. O custo é zero: sem cookie no escopo, nada
    // é enviado.
    credentials: "include",
  });
}

/**
 * A resposta crua, com autenticação e uma renovação em caso de 401.
 *
 * Existe para o download de CSV, que precisa do `Response` — do blob e do
 * `Content-Disposition` — e não de JSON desserializado. Reaproveita o mesmo
 * interceptor de `request` **de propósito**: sem isto, exportar depois de 15
 * minutos parado daria erro em vez de renovar o token, e cada chamador teria
 * sua própria cópia da lógica de refresh para sair de sincronia.
 */
export async function requestRaw(url: URL): Promise<Response> {
  const buscar = () => {
    const token = lerToken();
    return fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "include",
    });
  };

  const resposta = await buscar();
  if (resposta.status === 401 && (await aoReceber401())) return buscar();
  return resposta;
}

export async function request<T>(caminho: string, opcoes: Opcoes = {}): Promise<T> {
  let resposta = await enviar(caminho, opcoes);

  if (resposta.status === 401 && (await aoReceber401())) {
    // Uma única repetição. Se o 401 persistir depois de um refresh bem-sucedido,
    // o problema não é o token — repetir de novo viraria laço.
    resposta = await enviar(caminho, opcoes);
  }

  if (!resposta.ok) {
    throw new ApiError(resposta.status, await lerCorpo(resposta));
  }

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

/** Resposta paginada do DRF (`PageNumberPagination`). */
export type Pagina<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
