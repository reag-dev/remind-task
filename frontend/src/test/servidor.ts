import { setupServer } from "msw/node";

/**
 * Servidor de mocks sem handler padrão.
 *
 * Cada teste declara o que espera com `servidor.use(...)`. Um conjunto global de
 * handlers "que funcionam" tenderia a esconder exatamente o que se quer provar —
 * e o `onUnhandledRequest: "error"` do setup transforma qualquer rota não
 * declarada em falha visível, em vez de um fetch silencioso para a rede.
 */
export const servidor = setupServer();

export const API = "http://localhost:8000/api";
