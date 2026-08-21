import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { _limparEstadoDeRefresh } from "../auth/refresh.ts";
import { gravarAccessToken } from "../auth/sessao.ts";
import { servidor } from "./servidor.ts";

// `error` e não `warn`: uma chamada que escapou do mock é um teste que fala com
// a rede de verdade. Isso passa na máquina de quem tem o backend no ar e falha
// no CI — o pior modo de falha que uma suíte pode ter.
beforeAll(() => servidor.listen({ onUnhandledRequest: "error" }));

// O jsdom não implementa HTMLDialogElement: `showModal` e `close` simplesmente
// não existem no protótipo. Sem isto, todo teste que abre o DialogoConfirmar
// morre com "showModal is not a function".
//
// O que este stub NÃO cobre, e por isso não se testa aqui: foco preso dentro do
// diálogo, o resto da página virar inerte e o `::backdrop`. Essas são
// exatamente as razões de usar `<dialog>` nativo em vez de uma div, e são
// comportamento de browser — verificáveis só em teste de navegador de verdade.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function abrir(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function fechar(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
}

afterEach(() => {
  servidor.resetHandlers();
  cleanup();
  // O token e a promessa de refresh são estado de MÓDULO, então sobrevivem ao
  // fim do teste. Sem esta limpeza, um teste que autentica deixa o seguinte
  // começar logado.
  gravarAccessToken(null);
  _limparEstadoDeRefresh();
});

afterAll(() => servidor.close());
