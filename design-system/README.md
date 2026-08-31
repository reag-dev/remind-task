# @remind-task/design-system

Tokens e primitivas de UI extraídos do [remind-task](../frontend) — cor,
espaço, tipografia, raio e componentes base (botão, campo, cartão, diálogo,
badge, chip, alerta). CSS puro, sem dependência de framework, sem build.

Extraído das Phases 0-6 do [plano de design do
remind-task](../.claude/plans/remind-task-design-2026-08-26.md), depois
generalizado pelo [plano de extração](../.claude/plans/remind-task-design-system-pacote-2026-08-31.md).
Todo valor de cor/espaço/tipografia/raio é idêntico à fonte — só o nome
mudou, de português específico do domínio (tabelas com vencimento) para
inglês genérico.

## Instalar

Sem registro por enquanto. Empacote e instale o tarball local:

```bash
cd design-system
npm pack
# gera remind-task-design-system-0.1.0.tgz
cd /caminho/do/outro-projeto
npm install /caminho/para/remind-task-design-system-0.1.0.tgz
```

## Usar

```html
<link rel="stylesheet" href="node_modules/@remind-task/design-system/tokens.css" />
<link rel="stylesheet" href="node_modules/@remind-task/design-system/components.css" />
```

```html
<button class="button">Salvar</button>
<button class="button button--secondary">Cancelar</button>
<input class="field" placeholder="Nome" />
<span class="badge-status badge-status--danger">Atrasado</span>
```

Abra [`styleguide.html`](./styleguide.html) direto no browser (`file://`,
sem servidor) para ver cada token e componente renderizado.

## Tokens

### Cor

| Token | Valor | Uso |
|---|---|---|
| `--color-text` | `#1a1c1e` | texto padrão |
| `--color-background` | `#ffffff` | fundo da página |
| `--color-text-muted` | `#5c636a` | texto secundário |
| `--color-border` | `#d7dbdf` | bordas de campo/cartão |
| `--color-accent` | `#1b4dd8` | ação primária |
| `--color-on-accent` | `#ffffff` | texto sobre fundo saturado (botão, badge) |
| `--surface-subtle` | `#f3f4f6` | fundo neutro (campo desabilitado, `<code>`) |
| `--surface-elevated` | `#fafbfc` | realce sutil (hover de linha) |
| `--overlay` | `rgb(0 0 0 / 45%)` | scrim de diálogo |

### Estado (danger / warning / success)

Cada estado tem uma variante **sólida** (fundo preenchido — botão
destrutivo, badge) e um **trio tonal** texto/fundo/borda (alerta, selo de
status), com contraste verificado por `scripts/auditar-estilo.mjs`.

| Token | Valor |
|---|---|
| `--color-danger` | `#b3261e` |
| `--color-danger-text` / `-bg` / `-border` | `#8c1d18` / `#fceceb` / `#f0b4b0` |
| `--color-warning-text` / `-bg` / `-border` | `#8a4b00` / `#fff4e5` / `#f2c98a` |
| `--color-success` | `#0a7c42` |
| `--color-success-text` / `-bg` / `-border` | `#0a5c33` / `#eaf6ef` / `#a9d8bf` |

`warning` não tem variante sólida — a fonte (remind-task) nunca teve um
"aviso sólido", e este pacote não inventa cor que a fonte não tinha.

### Espaço, tipografia, forma

| Token | Valores |
|---|---|
| `--space-1` … `--space-6` | `0.25rem, 0.5rem, 0.75rem, 1rem, 1.5rem, 2rem` |
| `--font-size-1` … `--font-size-5` | `0.75rem, 0.8125rem, 0.875rem, 0.9375rem, 1.125rem` |
| `--radius-sm` / `--radius-lg` | `6px` / `8px` |
| `--border-width` | `1px` |

## Componentes

`.button` (+ `--secondary`, `--danger`, `--ghost`), `.field` / `.select` /
`.textarea`, `.card`, `.dialog` (+ `.dialog-actions`), `.badge`, `.chip`,
`.empty-state`, `.alert--{danger,warning,success}`,
`.badge-status--{danger,warning,success}`, `.text-muted`,
`.visually-hidden`. Foco visível (`:focus-visible`) é universal — cobre
input/select/textarea/button/a, inclusive dentro de `<dialog>`.

## O que não veio do remind-task

Deliberadamente fora deste pacote — são específicos do domínio de tabelas
com vencimento, não primitivas de design system:

- `.selo-*` (4 níveis: atrasado/hoje/em-breve/ok) → virou a tríade
  `danger`/`warning`/`success`. O nível "em-breve" (segundo tom de aviso)
  não tem equivalente aqui; projetos que precisarem de um terceiro nível
  definem `--color-warning-2` localmente.
- `.filtro-chip`, `table.grid`, paginação, exportação — UI de grid, não de
  design system.
- Tema escuro — os tokens preparam o terreno (um bloco
  `prefers-color-scheme` redefinindo as custom properties), mas não está
  implementado.
- Bindings de framework (componentes React/Vue) — só CSS, para não
  acoplar o pacote a uma stack.

## Verificar

```bash
node scripts/auditar-estilo.mjs         # cor fora do token + contraste (gate)
node scripts/auditar-estilo.mjs --tudo  # + espaçamento fora da escala (relatório)
```

Mesma régua do remind-task (`frontend/scripts/auditar-estilo.mjs`), lendo
`tokens.css` (só cor literal deve morar aqui) e `components.css` (só deve
consumir tokens).
