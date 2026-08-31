/**
 * Auditoria de estilo do pacote — adaptada de
 * frontend/scripts/auditar-estilo.mjs (remind-task), Phase 3 do plano de
 * extração (.claude/plans/remind-task-design-system-pacote-2026-08-31.md).
 *
 * Mesma lógica da fonte, mas lendo DOIS arquivos em vez de um:
 *   - tokens.css      — só o bloco `:root`, é de onde os tokens vêm.
 *   - components.css  — as regras que devem CONSUMIR os tokens, nunca
 *                        declarar cor/espaço cru.
 *
 * Mede três coisas, todas verificáveis por quem não participou da conversa:
 *
 *   1. COR FORA DO TOKEN — hex ou rgb() em `components.css`. Só `tokens.css`
 *      pode declarar cor literal.
 *   2. ESPAÇO FORA DA ESCALA — rem/px cru em padding, margin e gap, em
 *      `components.css`.
 *   3. CONTRASTE — razão WCAG dos pares (cor, fundo) que `components.css`
 *      declara, dois níveis (WCAG 2.1 §1.4.3): 4.5:1 texto normal, 3:1
 *      texto grande (24px+, ou 18.66px+ em negrito). Reprova por padrão,
 *      com ou sem `--tudo` — é acessibilidade, não preferência de estilo.
 *
 * ⚠️ Mesma ressalva da fonte: contraste de borda contra o próprio
 * preenchimento (WCAG 1.4.11) fica fora — inspeção manual, não gate.
 *
 * Códigos de saída: 0 aprovado, 1 há violação, 2 arquivo não encontrado.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const ARQ_TOKENS = join(RAIZ, "tokens.css");
const ARQ_COMPONENTES = join(RAIZ, "components.css");

const TUDO = process.argv.includes("--tudo");

const MINIMO_NORMAL = 4.5;
const MINIMO_GRANDE = 3.0;
const PX_GRANDE_NORMAL = 24;
const PX_GRANDE_NEGRITO = 18.66;
const PESO_NEGRITO = 700;

// ------------------------------------------------------------------ leitura

let cssTokens, cssComponentes;
try {
  cssTokens = readFileSync(ARQ_TOKENS, "utf8");
  cssComponentes = readFileSync(ARQ_COMPONENTES, "utf8");
} catch {
  console.error(`não encontrei ${ARQ_TOKENS} ou ${ARQ_COMPONENTES}`);
  process.exit(2);
}

const linhasComponentes = cssComponentes.split("\n");

// ------------------------------------------------------------------- tokens

/** `--nome: valor;` declarado em QUALQUER lugar de tokens.css. */
const tokens = new Map();
for (const linha of cssTokens.split("\n")) {
  const m = linha.match(/^\s*(--[\w-]+)\s*:\s*([^;]+);/);
  if (m) tokens.set(m[1], m[2].trim());
}

/** Resolve `var(--x)` até chegar a uma cor literal. Para em ciclo e em fallback. */
function resolver(valor, profundidade = 0) {
  if (profundidade > 10) return null;
  const m = valor?.match(/^var\(\s*(--[\w-]+)\s*\)$/);
  if (!m) return valor;
  const alvo = tokens.get(m[1]);
  return alvo ? resolver(alvo.trim(), profundidade + 1) : null;
}

// ------------------------------------------------------------------- cores

const HEX = /#[0-9a-fA-F]{3,8}\b/g;
const RGB = /\brgba?\([^)]*\)/g;

const coresForaDoToken = [];
linhasComponentes.forEach((linha, i) => {
  const achados = [...(linha.match(HEX) ?? []), ...(linha.match(RGB) ?? [])];
  for (const cor of achados) {
    coresForaDoToken.push({ linha: i + 1, cor, trecho: linha.trim() });
  }
});

// ------------------------------------------------------------------ espaços

const PROP_ESPACO = /^\s*(padding|margin|gap|row-gap|column-gap)(-\w+)?\s*:\s*([^;]+);/;
const VALOR_CRU = /(?<![\w-])\d*\.?\d+(rem|px|em)\b/;

const espacosForaDaEscala = [];
linhasComponentes.forEach((linha, i) => {
  const m = linha.match(PROP_ESPACO);
  if (!m) return;
  const valor = m[3];
  if (valor.includes("var(")) return;
  if (VALOR_CRU.test(valor)) {
    espacosForaDaEscala.push({ linha: i + 1, prop: m[1], valor: valor.trim() });
  }
});

// ---------------------------------------------------------------- contraste

function hexParaRgb(hex) {
  let h = hex.slice(1);
  if (h.length === 3) h = [...h].map((c) => c + c).join("");
  if (h.length === 8) h = h.slice(0, 6);
  if (h.length !== 6) return null;
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function paraRgb(valor) {
  if (!valor) return null;
  const v = valor.trim();
  if (v.startsWith("#")) return hexParaRgb(v);
  const m = v.match(/^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/);
  return m ? [+m[1], +m[2], +m[3]] : null;
}

/** `1.125rem` -> 18, `18px` -> 18. Assume raiz em 16px. */
function paraPx(valor) {
  if (!valor) return null;
  const v = valor.trim();
  const rem = v.match(/^(\d*\.?\d+)rem$/);
  if (rem) return parseFloat(rem[1]) * 16;
  const px = v.match(/^(\d*\.?\d+)px$/);
  return px ? parseFloat(px[1]) : null;
}

function luminancia([r, g, b]) {
  const c = [r, g, b]
    .map((v) => v / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function razao(corA, corB) {
  const a = luminancia(corA);
  const b = luminancia(corB);
  const [claro, escuro] = a > b ? [a, b] : [b, a];
  return (claro + 0.05) / (escuro + 0.05);
}

function paresDeclarados() {
  const pares = [];
  const fundoPadrao = resolver(tokens.get("--color-background") ?? "#ffffff");

  let seletor = null;
  let inicio = 0;
  let cor = null;
  let fundo = null;
  let tamanho = null;
  let peso = null;

  linhasComponentes.forEach((linha, i) => {
    const abre = linha.match(/^([^{}]+)\{\s*$/);
    if (abre) {
      seletor = abre[1].trim();
      inicio = i + 1;
      cor = null;
      fundo = null;
      tamanho = null;
      peso = null;
      return;
    }
    if (seletor === null) return;

    const mCor = linha.match(/^\s*color\s*:\s*([^;]+);/);
    if (mCor) cor = resolver(mCor[1].trim());

    const mFundo = linha.match(/^\s*background(-color)?\s*:\s*([^;]+);/);
    if (mFundo) {
      const primeiro = mFundo[2].trim().split(/\s+/)[0];
      fundo = resolver(primeiro);
    }

    const mTamanho = linha.match(/^\s*font-size\s*:\s*([^;]+);/);
    if (mTamanho) tamanho = resolver(mTamanho[1].trim());

    const mPeso = linha.match(/^\s*font-weight\s*:\s*([^;]+);/);
    if (mPeso) peso = resolver(mPeso[1].trim());

    if (/^\s*\}/.test(linha)) {
      if (cor) {
        const a = paraRgb(cor);
        const b = paraRgb(fundo ?? fundoPadrao);
        if (a && b) {
          const px = paraPx(tamanho);
          const negrito = peso !== null && parseInt(peso, 10) >= PESO_NEGRITO;
          const grande =
            px !== null && (px >= PX_GRANDE_NORMAL || (negrito && px >= PX_GRANDE_NEGRITO));
          pares.push({
            seletor,
            linha: inicio,
            cor,
            fundo: fundo ?? fundoPadrao,
            herdado: !fundo,
            razao: razao(a, b),
            grande,
            minimo: grande ? MINIMO_GRANDE : MINIMO_NORMAL,
          });
        }
      }
      seletor = null;
    }
  });

  return pares;
}

const pares = paresDeclarados();
const contrasteReprovado = pares.filter((p) => p.razao < p.minimo);

// ------------------------------------------------------------------- saída

const n = (x) => String(x).padStart(3);

console.log(`\nauditoria do pacote — design-system/tokens.css + components.css`);
console.log(`${linhasComponentes.length} linhas em components.css, ${tokens.size} tokens\n`);

console.log(`1. COR FORA DO TOKEN (em components.css) ... ${n(coresForaDoToken.length)}`);
for (const { linha, cor, trecho } of coresForaDoToken) {
  console.log(`     :${String(linha).padEnd(4)} ${cor.padEnd(9)} ${trecho}`);
}

console.log(`\n2. ESPAÇO FORA DA ESCALA .................... ${n(espacosForaDaEscala.length)}`);
for (const { linha, prop, valor } of espacosForaDaEscala.slice(0, 12)) {
  console.log(`     :${String(linha).padEnd(4)} ${prop.padEnd(8)} ${valor}`);
}
if (espacosForaDaEscala.length > 12) {
  console.log(`     … e mais ${espacosForaDaEscala.length - 12}`);
}

console.log(
  `\n3. CONTRASTE ................................. ${n(contrasteReprovado.length)} abaixo do mínimo (${MINIMO_NORMAL}:1 texto normal, ${MINIMO_GRANDE}:1 texto grande — de ${pares.length} pares lidos)`,
);
for (const p of pares.sort((a, b) => a.razao - b.razao).slice(0, 20)) {
  const marca = p.razao < p.minimo ? "REPROVA" : "  ok   ";
  const nota =
    (p.herdado ? " (fundo herdado de --color-background)" : "") +
    (p.grande ? " (texto grande, min 3:1)" : "");
  console.log(
    `     ${marca} ${p.razao.toFixed(2).padStart(6)}:1  ${p.cor} sobre ${p.fundo}  ${p.seletor}${nota}`,
  );
}

// ---------------------------------------------------------------- veredito

const falhas = [];
if (coresForaDoToken.length > 0) {
  falhas.push(`${coresForaDoToken.length} cores fora do token`);
}
if (contrasteReprovado.length > 0) {
  falhas.push(`${contrasteReprovado.length} pares abaixo do mínimo de contraste`);
}
if (TUDO && espacosForaDaEscala.length > 0) {
  falhas.push(`${espacosForaDaEscala.length} espaçamentos fora da escala`);
}

console.log("");
if (falhas.length > 0) {
  console.log(`REPROVADO — ${falhas.join("; ")}`);
  if (!TUDO && espacosForaDaEscala.length > 0) {
    console.log("(espaço ainda está em modo relatório; --tudo o faz reprovar)");
  }
  process.exit(1);
}

console.log("APROVADO");
