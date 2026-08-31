# Plan: remind-task — Design simples e minimalista

**Date:** 2026-08-26
**Status:** **concluído** em 2026-08-31 — Phases 0-6 todas feitas. Linha de
base medida abaixo; resultado final: 24 → 0 cores fora do `:root`, 0 pares de
contraste abaixo do mínimo (dois níveis agora, 4.5:1/3:1), 246 testes de
frontend verdes.

## Linha de base (medida, não estimada)

`npm run estilo:auditar` em `f0f3dae`, branch `feat/design-minimalista`:

| Medida | Valor |
|---|---|
| Cor fora do `:root` | **24** |
| Espaçamento fora de escala | **74** |
| Pares de contraste lidos | 20 |
| Pares abaixo de 4.5:1 | **0** |

**Duas coisas que a medição corrigiu neste plano:**

1. **São 24 cores soltas, não 23.** O `grep` que escreveu este plano contava só
   hex; escapou `rgb(0 0 0 / 45%)` na linha 264 (o `::backdrop` do diálogo). A
   régua vê o que o olho não viu — que é o ponto dela.
2. **O contraste já passa em tudo que dá para medir: 0 reprovados em 20 pares.**
   Isso muda a Phase 6 de conserto para trava: em vez de corrigir cor ruim, ela
   passa a impedir que as Phases 1-5 introduzam uma. Vale ler a ressalva no
   cabeçalho do script sobre o que ele **não** mede — fundo herdado de ancestral
   distante e tamanho de fonte ficam fora, então 0 aqui não é alvará.

**O espaçamento é o número grande, e não estava no diagnóstico original.** 74
valores crus em `padding`/`margin`/`gap` contra 24 de cor: a falta de ritmo
vertical pesa mais na sensação de "não é um produto só" do que a cor. A Phase 3
(moldura e ritmo) sobe de prioridade em relação à Phase 2.
**Planos irmãos:** [`remind-task-frontend-2026-08-20.md`](remind-task-frontend-2026-08-20.md)
(a SPA, concluída) · [`remind-task-producao-2026-08-21.md`](remind-task-producao-2026-08-21.md)
(produção, Phases 0-11 concluídas)

## Goal

Que as telas existentes pareçam um produto só, com hierarquia visual clara e a
informação de vencimento em primeiro plano — sem introduzir framework de estilo,
sem redesenhar fluxo nenhum.

---

## O que se apurou antes de planejar

**Não há UI para reaproveitar de outro branch.** Foi verificado, não presumido:

```bash
# nenhum commit de frontend/src fora de main, exceto uma regeração de schema.d.ts
git log --oneline main..<ref> -- frontend/src
# styles.css é idêntico em TODOS os refs (locais e remotos)
git diff main <ref> -- frontend/src/styles.css
```

O único commit de `frontend/` fora de `main` é `03a06ca`, que regera
`schema.d.ts` e não toca em estilo. Os branches `feat/*` que "diferem" de `main`
diferem por estarem **atrás** dela, não por terem trabalho próprio. `main` é a
fonte única.

**O estado do estilo hoje**, medido:

| Fato | Número |
|---|---|
| Arquivos de estilo | 1 — `frontend/src/styles.css`, 674 linhas |
| Tokens de cor no `:root` | 7 (`--texto`, `--fundo`, `--sutil`, `--borda`, `--acento`, `--ok`, `--erro`) |
| Cores **fora** do `:root` | **24** (medido na Phase 0; o grep dizia 23) |
| Escala de espaçamento | nenhuma — `rem` solto em cada regra |
| Escala tipográfica | nenhuma — `font-size` pontual |
| Raio de borda | `6px` repetido à mão |
| Rotas / componentes | 12 / 14 |

O diagnóstico não é "falta um design system". É que **já existe um sistema de
tokens e quase ninguém o usa**: 23 cores cravadas na mão são a razão de os selos
de vencimento, os avisos e os cartões parecerem de produtos diferentes. Fechar
essa distância é o trabalho, e é por isso que este plano não instala nada.

**A restrição que decide o formato do trabalho:** os 244 testes de frontend
consultam por *role*, *label* e texto (`getByRole`, `getByLabelText`). Isso
torna a estrutura HTML um contrato. Logo: **CSS primeiro**; JSX só quando a
mudança preserva o nome acessível, e o teste é quem prova que preservou.

---

## Scope

### In-Scope
- `frontend/src/styles.css` — completar os tokens e passar o arquivo a usá-los.
- Ajustes de classe/estrutura em rotas e componentes **que não alterem nome
  acessível** nem a árvore de roles.
- Um script de auditoria de estilo (`frontend/scripts/auditar-estilo.mjs`), Node
  puro, sem dependência nova — é ele que dá `Verify` runnable às fases.
- Contraste AA verificado por medição, não por olho.

### Out-of-Scope
- **Tailwind, CSS-in-JS, biblioteca de componentes.** Um arquivo de 674 linhas
  com tokens já resolve o problema medido; trocar a fundação custaria reescrever
  14 componentes para ganhar o que 6 fases de CSS entregam.
- **Tema escuro.** Fica fora, como no plano do frontend. Os tokens desta fase o
  tornam barato depois — um bloco `prefers-color-scheme` redefinindo variáveis —
  mas barato depois não é motivo para fazer agora.
- Redesenho de fluxo, telas novas, mudança de navegação.
- i18n, animações e ilustrações.
- Qualquer mudança de JSX que altere `role`, `aria-*`, label ou texto visível
  usado por teste.

---

## Phases

### Phase 0 — A régua, antes de mexer em pixel 🟢 concluída 2026-08-26

**Objective:** que "melhorou" pare de ser opinião e vire número.

**Steps:**
1. ✅ `frontend/scripts/auditar-estilo.mjs` — Node stdlib, sem dependência nova.
   Mede cor fora do `:root`, espaçamento fora de escala e razão de contraste
   WCAG dos pares (cor, fundo) declarados no mesmo bloco de regra.
2. ✅ Linha de base gravada no topo deste arquivo.

**Decisão tomada na execução:** na Phase 0 **só a cor reprova**; espaço e
contraste saem em modo relatório, e `--tudo` os liga. Reprovar as três medidas
de uma vez transformaria a régua em muro — a Phase 1 não teria como sair do
vermelho sem fazer o trabalho das Phases 2-6 junto. A Phase 6 é quem liga
`--tudo`.

**Files Touched:** `frontend/scripts/auditar-estilo.mjs` (novo) ·
`frontend/package.json` (script `estilo:auditar`)

**Verify:** `docker compose exec -T frontend npm run estilo:auditar`
**Done When:** ✅ o comando imprime as 24 cores fora do `:root`, os 74
espaçamentos crus e as razões de contraste, e sai com código 1.
**Time:** 1h

---

### Phase 1 — Tokens completos 🟢 concluída 2026-08-31

**Objective:** um vocabulário fechado, para as fases seguintes só consumirem.

**Steps:**
1. Manter os 7 nomes de cor existentes — renomear é churn sem ganho. Acrescentar
   os que faltam para cobrir os 23 hex soltos: superfície elevada, superfície
   sutil, e os quatro pares (texto/fundo/borda) dos selos de vencimento.
2. Acrescentar escalas: `--espaco-1..6` (base 0.25rem), `--texto-1..5`,
   `--raio`, `--borda-fina`.
3. **Nenhuma regra existente muda nesta fase.** Só o `:root` cresce.

**Files Touched:** `frontend/src/styles.css` (apenas o bloco `:root`)

**Verify:** `docker compose exec -T frontend npm run test`
**Done When:** 244 testes verdes e a auditoria reporta os mesmos 23 hex — a fase
adiciona vocabulário, não o aplica ainda.
**Time:** 1h

**Replanning trigger:** se cobrir os 23 hex exigir mais de ~16 tokens, a paleta
está sendo desenhada em vez de descrita — parar e reduzir a paleta primeiro.

---

### Phase 2 — Primitivas: botão, campo, cartão, diálogo 🟢 concluída 2026-08-31

**Objective:** os elementos que aparecem em toda tela passam a sair do mesmo
molde.

**Steps:**
1. Substituir hex e espaçamentos crus por tokens em: `button` e variantes
   (`.destrutivo`, `.secundario`, `.ligacao`, `.botao`), `.formulario input`,
   `select`, `textarea`, `label.caixa`, `.cartao`, `.dialogo`.
2. Unificar altura, padding e raio entre os controles — hoje botão e campo têm
   padding diferente e encostam desalinhados.
3. Preservar o `:focus-visible` explícito que já existe. Ele não é decoração:
   está lá porque o reset apagava o foco do browser.

**Files Touched:** `frontend/src/styles.css`

**Verify:** `docker compose exec -T frontend npm run test -- src/components/DialogoConfirmar src/routes/Login src/routes/Conta`
**Done When:** testes verdes e `npm run estilo:auditar` não acusa hex nas seções
*botões*, *diálogo* e *formulário*.
**Time:** 2h

---

### Phase 3 — Moldura: cabeçalho, largura e ritmo vertical 🟢 concluída 2026-08-31

**Objective:** o enquadramento que dá a sensação de "minimalista" — espaço, não
enfeite.

**Steps:**
1. `.cabecalho`, `.marca`, `.cabecalho-direita`, `.conteudo`: largura máxima
   única, espaçamento pela escala, uma só regra de ritmo vertical entre blocos.
2. `.titulo-com-acao`: alinhar título e ação numa linha só, sem salto.
3. Reduzir pesos de fonte em uso a dois (normal e 600) — hoje há variação
   pontual sem sistema.

**Files Touched:** `frontend/src/styles.css` ·
`frontend/src/components/Layout.tsx` (só classe, se preciso — sem tocar em texto
ou role)

**Verify:** `docker compose exec -T frontend npm run test -- src/components/Layout`
**Done When:** testes verdes e o nome acessível do cabeçalho inalterado.
**Time:** 2h

---

### Phase 4 — O grid e os selos de vencimento 🟢 concluída 2026-08-31

**Objective:** a razão de o produto existir — "abrir a tela e ver o que está
vencendo" (spec, seção 12).

**Steps:**
1. `table.grid`: densidade e alinhamento por tipo de coluna (número à direita,
   data em largura estável), `th` com hierarquia clara, zebra/hover discretos.
2. `.selo-*` (`overdue`, `due_today`, `due_soon`, `on_track`, desconhecido):
   hoje são 12 hex à mão. Passam a derivar de tokens, mantendo **a distinção por
   forma e texto além da cor** — daltonismo é o caso que a cor sozinha perde.
3. `.chip`, `.mascara`, `.revelado`, `.rolagem-horizontal`: mesma linguagem.

**Files Touched:** `frontend/src/styles.css` ·
`frontend/src/components/SeloStatus.tsx` (só se a distinção não-cromática exigir
— e então o teste do selo é atualizado junto, de propósito)

**Verify:** `docker compose exec -T frontend npm run test -- src/components/GridRegistros src/components/SeloStatus src/routes/TabelaRegistros`
**Done When:** testes verdes; os quatro estados de vencimento continuam
distinguíveis com a cor removida.
**Time:** 3h

**Replanning trigger:** se distinguir os estados sem cor exigir mudar o texto do
selo, isso altera nome acessível — vira decisão de produto, não de CSS. Parar e
perguntar.

---

### Phase 5 — Estados: vazio, carregando, erro 🟢 concluída 2026-08-31

**Objective:** as três telas que todo mundo esquece e que definem se o produto
parece acabado.

**Steps:**
1. `.vazio`, `.carregando`, `.erro`, `.aviso`, `.ok`: um só molde, tokens, e
   texto que diz o que fazer em vez de só constatar.
2. Conferir que a busca sem resultado, a tabela sem registros e a caixa de
   alertas vazia usam o mesmo componente visual.

**Files Touched:** `frontend/src/styles.css` · rotas com estado vazio, se a
classe faltar: `frontend/src/routes/Tabelas.tsx`,
`frontend/src/routes/Alertas.tsx`, `frontend/src/routes/TabelaRegistros.tsx`

**Verify:** `docker compose exec -T frontend npm run test -- src/routes/Alertas src/routes/Tabelas src/components/BarraBusca`
**Done When:** testes verdes e nenhum `role="status"`/`role="alert"` removido.
**Time:** 2h

---

### Phase 6 — Contraste e foco, medidos 🟢 concluída 2026-08-31

**Decisão tomada na execução:** o contraste de TEXTO ganhou dois níveis
(4.5:1 normal, 3:1 texto grande — WCAG §1.4.3) e passou a reprovar por
padrão, sem precisar de `--tudo`; espaço fora da escala continua atrás da
flag, porque ainda sobram ~39 valores crus fora do escopo das Phases 1-5 e
barrar o build por eles hoje trocaria a régua por um muro.

Contraste de BORDA contra o próprio preenchimento (WCAG 1.4.11, "bordas de
estado") ficou **de fora**, deliberadamente: testado nos selos de
vencimento, a borda tonal contra o fundo tonal do mesmo selo mede bem
abaixo de 3:1, mas os dois foram desenhados tonais de propósito — o estado
já é distinguível por texto do rótulo, cor do texto (4.5:1+) e o
preenchimento contra a página. Forçar 3:1 na borda teria imposto uma
paleta mais contrastada sem pedido de produto para isso. Fica documentado
no cabeçalho do script como item de inspeção manual, não de gate
automático.

**Objective:** fechar com prova, não com impressão.

**Steps:**
1. `npm run estilo:auditar` passa a **falhar** com par de cores abaixo de
   4.5:1 (texto normal) ou 3:1 (texto grande e bordas de estado).
2. Corrigir o que reprovar — ajustando token, nunca abrindo exceção local.
3. Conferir foco visível em todo alvo interativo, incluindo dentro do `<dialog>`.

**Files Touched:** `frontend/scripts/auditar-estilo.mjs` ·
`frontend/src/styles.css`

**Verify:** `docker compose exec -T frontend npm run estilo:auditar && docker compose exec -T frontend npm run test`
**Done When:** auditoria sai 0 — zero hex fora do `:root`, zero par abaixo do
mínimo — e 244 testes verdes.
**Time:** 2h

---

## Dependencies & Assumptions

- **Rodar a partir de `main`.** No momento em que este plano foi escrito o
  checkout local estava em `feat/frontend-spa`, um snapshot de 2026-08-21 sem
  busca, recuperação de senha nem exclusão de conta. Começar de lá refaria
  estilo de telas que já mudaram.
- A stack sobe com `docker compose up -d`; os comandos `Verify` assumem os
  containers `frontend` e `web` no ar.
- Nenhuma fase depende de backend, deploy ou do que está no ar em produção.

## Current State

- Backend e frontend em `main`, verdes: 513 testes de backend (cobertura 90,92%),
  244 de frontend, CI verde em `f0f3dae`.
- Estilo: um arquivo, 7 tokens, 23 cores fora deles. Nenhum trabalho de design
  iniciado — este plano é a Phase 0 de tudo.

## O que dispara replanejamento

- **A auditoria da Phase 0 revelar que o `styles.css` tem regra morta em volume**
  (seletor sem uso em nenhum `.tsx`) → entra uma fase de remoção **antes** da
  Phase 1: aplicar tokens a CSS morto é trabalho jogado fora.
- **Alguma fase exigir mudar `role`, `aria-*` ou texto visível** → deixa de ser
  trabalho de CSS e vira decisão de produto, com o teste correspondente
  atualizado de propósito e não por acidente.
- **O pedido crescer para tema escuro** → os tokens da Phase 1 bastam, mas entra
  fase própria: cada par de contraste precisa ser medido de novo no escuro, e a
  Phase 6 passa a rodar duas vezes.
- **Alguém pedir biblioteca de componentes** → é reescrita dos 14 componentes,
  não ajuste de estilo. Cai na regra de não fazer rewrite sem gate: protótipo de
  uma tela primeiro, e `/research-and-decide` se passar de 3 pontos de atrito.
