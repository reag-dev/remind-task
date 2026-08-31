# Plan: design system genérico e reutilizável (extraído do remind-task)

**Date:** 2026-08-31
**Status:** **concluído** em 2026-08-31 — Phases 1-4 todas feitas.
`design-system/` empacotado, `node design-system/scripts/auditar-estilo.mjs`
sai APROVADO (0 cor fora do token, 0 espaço fora da escala, 0 par de
contraste abaixo do mínimo), `styleguide.html` conferido visualmente via
Playwright (paleta, escalas, botões, campos, cartão, diálogo com backdrop,
badge/chip/vazio, tríade danger/warning/success).

## Goal

Extrair os tokens e as primitivas de `frontend/src/styles.css` — já consolidados
nas Phases 0-6 do [plano de design](remind-task-design-2026-08-26.md) — para um
pacote autocontido em `design-system/`, com nomes genéricos (não específicos do
domínio de tabelas/vencimentos do remind-task), documentado e portável para
outros projetos.

## O que já existe (não redesenhar)

`frontend/src/styles.css` (674→751 linhas) já tem exatamente o material-fonte:
37 tokens no `:root` (superfícies, família de cor dos selos, escalas de
espaço/tipografia/raio), botão/campo/cartão/diálogo unificados, contraste
verificado em dois níveis via `frontend/scripts/auditar-estilo.mjs`. Este plano
**extrai e generaliza**, não reprojeta — qualquer decisão visual nova (cor,
proporção) é regressão de escopo.

## Scope

### In-Scope
- `design-system/tokens.css` — os mesmos tokens, renomeados para inglês
  genérico (`--color-text`, `--space-1`, `--font-size-1`, `--radius-sm`...) e
  reduzidos de 4 famílias de selo (atrasado/hoje/em-breve/ok, específicas de
  "vencimento") para a tríade padrão de UI: `--color-danger`,
  `--color-warning`, `--color-success` (cada uma com par texto/fundo/borda).
- `design-system/components.css` — as primitivas já construídas (botão, campo,
  cartão, diálogo, badge, chip, estado vazio, foco universal), com seletores
  genéricos (classes em inglês, não `.selo-overdue`/`.formulario`).
- `design-system/styleguide.html` — página estática (sem build) que renderiza
  cada token e componente, para revisão visual sem precisar montar um projeto.
- `design-system/scripts/auditar-estilo.mjs` — adaptação do script já
  existente (mesma lógica: cor fora do token, espaço fora da escala,
  contraste em dois níveis) apontando para os arquivos do pacote.
- `design-system/package.json` + `design-system/README.md` — nome, versão,
  `exports` apontando para `tokens.css`/`components.css`, tabela de tokens e
  exemplos de uso no README.

### Out-of-Scope
- Publicar no npm ou em qualquer registro — fica pronto para `npm pack`, não
  publicado.
- Migrar `frontend/` do remind-task para consumir o pacote novo. É um projeto
  à parte, depois que o pacote existir e for validado num segundo consumidor.
- Bindings de framework (componentes React/Vue) — só CSS, para não acoplar o
  pacote a uma stack.
- Tema escuro — mesma decisão do plano original, tokens já preparam o terreno
  mas não é este o momento.
- Qualquer cor, proporção ou raio novo. Se o styleguide "parecer faltando
  algo", a resposta é ir buscar no `styles.css` do remind-task, não inventar.

---

## Phases

### Phase 1 — Tokens genéricos 🟢 concluída 2026-08-31

**Objective:** vocabulário de design em nomes que fazem sentido fora do
domínio de tabelas com vencimento.

**Steps:**
1. Copiar o bloco `:root` de `frontend/src/styles.css` para
   `design-system/tokens.css`, sob `:root` e também como custom properties
   exportáveis (sem seletor de componente).
2. Renomear para inglês, mantendo o VALOR idêntico:
   `--texto→--color-text`, `--fundo→--color-background`,
   `--sutil→--color-text-muted`, `--borda→--color-border`,
   `--acento→--color-accent`, `--ok→--color-success-text` (ver passo 3),
   `--erro→--color-danger-text`, `--sobre-acento→--color-on-accent`,
   `--superficie-sutil→--surface-subtle`,
   `--superficie-elevada→--surface-elevated`, `--superposicao→--overlay`,
   `--espaco-N→--space-N`, `--texto-N→--font-size-N`, `--raio→--radius-sm`,
   `--raio-grande→--radius-lg`, `--borda-fina→--border-width`.
3. Reduzir os 4 pares de selo (atrasado/hoje/em-breve/ok) à tríade
   `--color-danger-{text,bg,border}` (= atrasado), `--color-warning-{...}`
   (= hoje — a cor mais saturada dos dois avisos, não a média), e
   `--color-success-{...}` (= ok). "Em-breve" fica documentado no README como
   variação que o remind-task tem e o pacote genérico não carrega — projetos
   que precisarem de um terceiro nível de aviso criam `--color-warning-2`
   localmente, fora do pacote.
4. Rodar `design-system/scripts/auditar-estilo.mjs --tudo` (adaptado na
   Phase 3) só depois que ela existir — nesta fase, conferir a olho que todo
   valor bateu com o original (`diff` mental contra o `:root` fonte).

**Files Touched:** `design-system/tokens.css` (novo)
**Verify:** `node -e "require('fs').readFileSync('design-system/tokens.css','utf8').match(/#[0-9a-fA-F]{3,8}/g).length === 20 || process.exit(1)"` — 20 é o número de valores hex esperados na tríade + acento/texto/fundo/etc.; ajustar o número ao terminar a Phase 1, não adivinhar antes.
**Done When:** `tokens.css` existe, todo nome é inglês/genérico, nenhum valor de cor mudou em relação ao `frontend/src/styles.css` fonte.
**Time:** 1h30

**Replanning trigger:** se a tríade danger/warning/success perder informação
que algum caso de uso genérico claramente precisa (não é o caso do
remind-task — é o caso do PACOTE), parar e reconsiderar 4 níveis antes de
prosseguir para a Phase 2.

---

### Phase 2 — Componentes genéricos 🟢 concluída 2026-08-31

**Objective:** as primitivas (botão, campo, cartão, diálogo, badge, chip,
estado vazio, foco) em seletores que não amarram a nenhum domínio.

**Steps:**
1. Copiar as regras de botão/campo/cartão/diálogo/badge/chip/vazio/foco de
   `frontend/src/styles.css` para `design-system/components.css`, consumindo
   `tokens.css`.
2. Trocar seletores específicos do remind-task por classes genéricas:
   `.botao/.secundario/.destrutivo/.ligacao → .button/.button--secondary/
   .button--danger/.button--ghost`; `.formulario input/select/textarea →
   .field/.select/.textarea` (ou atributo `[data-field]`, decidir na
   implementação pelo que ficar mais idiomático); `.cartao → .card`;
   `.dialogo → .dialog`; `.chip → .chip` (já genérico); `.vazio →
   .empty-state`; `.badge → .badge`.
3. **Não** trazer `.selo-*`, `.aviso`, `.filtro-chip`, `table.grid`,
   paginação — são específicos de grid/vencimento, não primitivas de design
   system. Só a tríade de cor (Phase 1) representa esse conceito no pacote
   genérico.
4. Preservar o `:focus-visible` universal (Phase 6 do plano original) —
   igual, com nomes de token trocados.

**Files Touched:** `design-system/components.css` (novo)
**Verify:** `docker compose exec -T frontend npm run test -- src/components/DialogoConfirmar src/routes/Login` — continua rodando os testes do remind-task, que não devem ter sido tocados (o pacote é lido, não importado ainda). É uma checagem de "nada no remind-task quebrou", não do pacote em si.
**Done When:** `components.css` cobre botão/campo/cartão/diálogo/badge/chip/vazio/foco, zero seletor com nome em português ou referência a vencimento/selo.
**Time:** 2h

---

### Phase 3 — Régua do pacote 🟢 concluída 2026-08-31

**Objective:** o mesmo tipo de prova mecânica que a Phase 0 do plano original
deu ao remind-task, agora para o pacote.

**Steps:**
1. Copiar `frontend/scripts/auditar-estilo.mjs` para
   `design-system/scripts/auditar-estilo.mjs`, apontando para
   `tokens.css`+`components.css` em vez de um `styles.css` único (ajustar a
   leitura para dois arquivos, mantendo a mesma lógica de cor/espaço/contraste
   em dois níveis).
2. Adicionar `design-system/package.json` com um script `auditar` chamando o
   script acima.

**Files Touched:** `design-system/scripts/auditar-estilo.mjs` (novo),
`design-system/package.json` (novo, mínimo — nome, versão, script)
**Verify:** `node design-system/scripts/auditar-estilo.mjs`
**Done When:** sai `APROVADO` — 0 cor fora do token, 0 par de contraste abaixo do mínimo.
**Time:** 1h

---

### Phase 4 — Styleguide e documentação 🟢 concluída 2026-08-31

**Objective:** alguém de fora do remind-task consegue olhar uma página e
entender o que o pacote oferece, sem montar projeto nenhum.

**Steps:**
1. `design-system/styleguide.html` — HTML estático que importa
   `tokens.css`+`components.css` por `<link>` relativo e renderiza: a paleta
   (nome do token + amostra), a escala de espaço, a escala tipográfica, e
   cada componente (botão nas 4 variantes, campo, cartão, diálogo aberto,
   badge, chip, estado vazio).
2. `design-system/README.md` — o que é, como instalar (`npm pack` +
   instalar o tarball, por enquanto — sem registro), tabela de tokens com
   nome/valor/uso, um exemplo de HTML mínimo usando `.button`+`.field`.
3. `design-system/package.json` completo: `name`, `version: 0.1.0`, `files`
   (`tokens.css`, `components.css`, `README.md`), `exports` para os dois CSS.

**Files Touched:** `design-system/styleguide.html` (novo),
`design-system/README.md` (novo), `design-system/package.json` (completar)
**Verify:** abrir `design-system/styleguide.html` direto no browser (`file://`) — não precisa de servidor, é a prova de que o pacote é autocontido.
**Done When:** todo token e componente do pacote aparece na página, README explica instalação e uso sem depender de contexto do remind-task.
**Time:** 2h

---

## Dependencies & Assumptions

- Depende do plano de design original (`remind-task-design-2026-08-26.md`,
  Phases 0-6) estar completo — está, mergeado via PR #20 e #21.
- Assume que "reutilizável" por ora significa "pacote autocontido, pronto
  para instalar via tarball local", não publicação em registro — se o
  usuário quiser publicar, isso é uma fase nova, não implícita nesta.
- Não depende de nada do backend Django.

## Current State

- Nada do pacote existe ainda — este plano começa do zero em cima do que já
  está pronto no `frontend/src/styles.css`.

## Notes

- Convenção de nomes decidida neste plano (não deriva de padrão externo
  específico): tokens em inglês kebab-case (`--color-*`, `--space-*`,
  `--font-size-*`, `--radius-*`), classes de componente também em inglês
  (`.button`, `.card`, `.dialog`...). É a convenção mais portável para um
  pacote que outros projetos vão ler sem o contexto em português do
  remind-task.
- A tríade danger/warning/success (em vez dos 4 níveis de selo do
  remind-task) é a maior simplificação deste plano — documentada na Phase 1
  para não ser lida como perda acidental.
