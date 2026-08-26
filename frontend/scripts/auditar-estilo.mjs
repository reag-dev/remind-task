/**
 * Auditoria de estilo — a régua da Phase 0 do plano de design.
 *
 * Existe para que "melhorou" pare de ser opinião. Mede três coisas em
 * `src/styles.css`, todas verificáveis por quem não participou da conversa:
 *
 *   1. COR FORA DO TOKEN — hex ou rgb() escrito fora do bloco `:root`. É o
 *      defeito que motivou o plano: existe um sistema de tokens e o arquivo
 *      quase não o usa, e é por isso que selo, aviso e cartão parecem de
 *      produtos diferentes.
 *   2. ESPAÇO FORA DA ESCALA — rem/px cru em padding, margin e gap. Sem escala,
 *      cada regra escolhe o próprio ritmo e nenhuma tela fica alinhada com a
 *      outra.
 *   3. CONTRASTE — razão WCAG dos pares (cor, fundo) que o CSS declara. Aqui a
 *      medição vale mais que o olho: o par que reprova costuma ser justamente o
 *      que parece bonito na tela de quem escolheu.
 *
 * Node puro, sem dependência nova. A fórmula de contraste é a da WCAG 2.1
 * (relative luminance + (L1+0.05)/(L2+0.05)), umas vinte linhas — não vale um
 * pacote.
 *
 * ⚠️ O QUE ELE NÃO MEDE, para ninguém ler um 0 como alvará:
 *
 * Ele lê CSS, não a tela. Um par (cor, fundo) só é conferido quando as duas
 * declarações estão NO MESMO bloco de regra; texto que herda o fundo de um
 * ancestral distante passa despercebido. Também não sabe de tamanho de fonte —
 * aplica 4.5:1 a tudo, que é o limite do texto normal, e por isso erra para o
 * lado seguro em título grande. Contraste de imagem, foco e movimento estão
 * fora: são inspeção, não parsing.
 *
 * Códigos de saída
 * ----------------
 *   0  nenhuma violação do que está LIGADO no momento
 *   1  há violação
 *   2  o arquivo de estilo não foi encontrado
 *
 * Na Phase 0 só as cores fora do token reprovam — é a linha de base, e reprovar
 * tudo de uma vez transformaria o script num muro em vez de uma régua. A Phase 6
 * liga o resto com `--tudo`.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const ARQUIVO = join(RAIZ, "src", "styles.css");

const TUDO = process.argv.includes("--tudo");

// Mínimos da WCAG 2.1 AA. O 3.0 vale para texto grande (>=18.66px negrito ou
// >=24px) e para limite de componente — como não dá para saber o tamanho lendo
// só a declaração de cor, o script cobra 4.5 e diz quando o caso é de fronteira.
const MINIMO_TEXTO = 4.5;

// ------------------------------------------------------------------ leitura

let css;
try {
  css = readFileSync(ARQUIVO, "utf8");
} catch {
  console.error(`não encontrei ${ARQUIVO}`);
  process.exit(2);
}

const linhas = css.split("\n");

/** Intervalo de linhas do bloco `:root` — é a única região onde hex é legítimo. */
function faixaDoRoot() {
  const inicio = linhas.findIndex((l) => /^\s*:root\s*\{/.test(l));
  if (inicio === -1) return [-1, -1];
  for (let i = inicio; i < linhas.length; i++) {
    if (/^\s*\}/.test(linhas[i])) return [inicio, i];
  }
  return [inicio, linhas.length - 1];
}

const [rootInicio, rootFim] = faixaDoRoot();
const dentroDoRoot = (i) => i >= rootInicio && i <= rootFim;

// ------------------------------------------------------------------- tokens

/** `--nome: valor;` declarado no `:root`. */
const tokens = new Map();
for (let i = rootInicio + 1; i < rootFim; i++) {
  const m = linhas[i].match(/^\s*(--[\w-]+)\s*:\s*([^;]+);/);
  if (m) tokens.set(m[1], m[2].trim());
}

/** Resolve `var(--x)` até chegar a uma cor literal. Para em ciclo e em fallback. */
function resolver(valor, profundidade = 0) {
  if (profundidade > 10) return null;
  const m = valor.match(/^var\(\s*(--[\w-]+)\s*\)$/);
  if (!m) return valor;
  const alvo = tokens.get(m[1]);
  return alvo ? resolver(alvo.trim(), profundidade + 1) : null;
}

// ------------------------------------------------------------------- cores

const HEX = /#[0-9a-fA-F]{3,8}\b/g;
const RGB = /\brgba?\([^)]*\)/g;

const coresForaDoToken = [];
linhas.forEach((linha, i) => {
  if (dentroDoRoot(i)) return;
  const achados = [...(linha.match(HEX) ?? []), ...(linha.match(RGB) ?? [])];
  for (const cor of achados) {
    coresForaDoToken.push({ linha: i + 1, cor, trecho: linha.trim() });
  }
});

// ------------------------------------------------------------------ espaços

// Só onde espaçamento realmente mora. `border-radius` e `font-size` têm escala
// própria e entram na Phase 1 — cobrá-los aqui misturaria dois problemas.
const PROP_ESPACO = /^\s*(padding|margin|gap|row-gap|column-gap)(-\w+)?\s*:\s*([^;]+);/;
// `0` não tem unidade e não precisa de token; `auto` e `100%` também não.
const VALOR_CRU = /(?<![\w-])\d*\.?\d+(rem|px|em)\b/;

const espacosForaDaEscala = [];
linhas.forEach((linha, i) => {
  if (dentroDoRoot(i)) return;
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
  if (h.length === 8) h = h.slice(0, 6); // ignora alfa: não dá para compor sem saber o que está atrás
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

/** Luminância relativa, WCAG 2.1. */
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

/**
 * Pares (cor, fundo) que o CSS declara no MESMO bloco.
 *
 * Blocos que declaram só um dos dois são comparados com `--fundo`, que é o
 * fundo do documento — a aproximação certa na maioria dos casos, e explicitada
 * na saída para ninguém confundir medição com suposição.
 */
function paresDeclarados() {
  const pares = [];
  const fundoPadrao = resolver(tokens.get("--fundo") ?? "#ffffff");

  let seletor = null;
  let inicio = 0;
  let cor = null;
  let fundo = null;

  linhas.forEach((linha, i) => {
    if (dentroDoRoot(i)) return;

    const abre = linha.match(/^([^{}]+)\{\s*$/);
    if (abre) {
      seletor = abre[1].trim();
      inicio = i + 1;
      cor = null;
      fundo = null;
      return;
    }
    if (seletor === null) return;

    const mCor = linha.match(/^\s*color\s*:\s*([^;]+);/);
    if (mCor) cor = resolver(mCor[1].trim());

    const mFundo = linha.match(/^\s*background(-color)?\s*:\s*([^;]+);/);
    if (mFundo) {
      // `background` pode trazer mais que cor; a primeira palavra basta aqui.
      const primeiro = mFundo[2].trim().split(/\s+/)[0];
      fundo = resolver(primeiro);
    }

    if (/^\s*\}/.test(linha)) {
      if (cor) {
        const a = paraRgb(cor);
        const b = paraRgb(fundo ?? fundoPadrao);
        if (a && b) {
          pares.push({
            seletor,
            linha: inicio,
            cor,
            fundo: fundo ?? fundoPadrao,
            herdado: !fundo,
            razao: razao(a, b),
          });
        }
      }
      seletor = null;
    }
  });

  return pares;
}

const pares = paresDeclarados();
const contrasteReprovado = pares.filter((p) => p.razao < MINIMO_TEXTO);

// ------------------------------------------------------------------- saída

const n = (x) => String(x).padStart(3);

console.log(`\nauditoria de estilo — ${ARQUIVO.replace(RAIZ, "frontend")}`);
console.log(`${linhas.length} linhas, ${tokens.size} tokens no :root\n`);

console.log(`1. COR FORA DO TOKEN ......... ${n(coresForaDoToken.length)}`);
for (const { linha, cor, trecho } of coresForaDoToken) {
  console.log(`     :${String(linha).padEnd(4)} ${cor.padEnd(9)} ${trecho}`);
}

console.log(`\n2. ESPAÇO FORA DA ESCALA ..... ${n(espacosForaDaEscala.length)}`);
for (const { linha, prop, valor } of espacosForaDaEscala.slice(0, 12)) {
  console.log(`     :${String(linha).padEnd(4)} ${prop.padEnd(8)} ${valor}`);
}
if (espacosForaDaEscala.length > 12) {
  console.log(`     … e mais ${espacosForaDaEscala.length - 12}`);
}

console.log(
  `\n3. CONTRASTE ................. ${n(contrasteReprovado.length)} abaixo de ${MINIMO_TEXTO}:1 (de ${pares.length} pares lidos)`,
);
for (const p of pares.sort((a, b) => a.razao - b.razao).slice(0, 12)) {
  const marca = p.razao < MINIMO_TEXTO ? "REPROVA" : "  ok   ";
  const nota = p.herdado ? " (fundo herdado de --fundo)" : "";
  console.log(
    `     ${marca} ${p.razao.toFixed(2).padStart(6)}:1  ${p.cor} sobre ${p.fundo}  ${p.seletor}${nota}`,
  );
}

// ---------------------------------------------------------------- veredito

const falhas = [];
if (coresForaDoToken.length > 0) {
  falhas.push(`${coresForaDoToken.length} cores fora do :root`);
}
if (TUDO) {
  if (espacosForaDaEscala.length > 0) {
    falhas.push(`${espacosForaDaEscala.length} espaçamentos fora da escala`);
  }
  if (contrasteReprovado.length > 0) {
    falhas.push(`${contrasteReprovado.length} pares abaixo de ${MINIMO_TEXTO}:1`);
  }
}

console.log("");
if (falhas.length > 0) {
  console.log(`REPROVADO — ${falhas.join("; ")}`);
  if (!TUDO) {
    console.log("(espaço e contraste estão em modo relatório; --tudo os faz reprovar)");
  }
  process.exit(1);
}

console.log("APROVADO");
