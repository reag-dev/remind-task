import { useEffect, useRef, useState } from "react";

/**
 * Campo de busca dos registros.
 *
 * O estado da verdade é a URL (`useTabelaServidor`), como o dos demais filtros.
 * Mas digitar direto na URL dispararia uma requisição por tecla, então o
 * componente mantém um rascunho local e só o promove depois de uma pausa.
 */

/**
 * Pausa antes de buscar.
 *
 * 350 ms é o intervalo em que uma pausa ainda parece parte da digitação. Abaixo
 * de ~250 ms uma pessoa que digita devagar dispara requisições no meio da
 * palavra; acima de ~500 ms o campo começa a parecer travado.
 */
const ESPERA_MS = 350;

type Props = {
  /** Termo vindo da URL — a fonte da verdade. */
  valor: string;
  onBuscar: (termo: string) => void;
};

export function BarraBusca({ valor, onBuscar }: Props) {
  const [rascunho, setRascunho] = useState(valor);

  // A referência evita que o efeito abaixo dependa de `onBuscar`: o pai o
  // recria a cada render, e a dependência reiniciaria o temporizador em toda
  // renderização — o debounce nunca chegaria ao fim numa tela que re-renderiza.
  const buscar = useRef(onBuscar);
  useEffect(() => {
    buscar.current = onBuscar;
  }, [onBuscar]);

  // Sincroniza quando a URL muda por FORA do campo: botão "voltar", "limpar
  // filtros", ou um link colado. Sem isto o campo mostraria o termo antigo
  // enquanto a lista já exibe outro resultado.
  //
  // Ajuste durante a renderização, e não num `useEffect`: é o padrão que a
  // documentação do React indica para "state derivado de prop", e o efeito
  // equivalente renderiza duas vezes — o usuário chega a ver o valor velho por
  // um quadro. O `react-hooks/set-state-in-effect` reprova a outra forma.
  const [valorAnterior, setValorAnterior] = useState(valor);
  if (valor !== valorAnterior) {
    setValorAnterior(valor);
    setRascunho(valor);
  }

  useEffect(() => {
    // Nada a fazer quando o rascunho já é o que está na URL — inclusive na
    // montagem e logo depois da sincronização acima. Sem esta saída, abrir uma
    // URL com `?busca=` já preenchido dispararia uma navegação redundante.
    if (rascunho === valor) return;

    const id = setTimeout(() => buscar.current(rascunho), ESPERA_MS);
    return () => clearTimeout(id);
  }, [rascunho, valor]);

  return (
    <search className="barra-busca">
      {/* `role="search"` explícito: o elemento `<search>` é recente e leitores
          de tela mais antigos ainda não derivam o papel dele sozinhos. */}
      <div role="search">
        <label htmlFor="busca-registros" className="sutil">
          Buscar
        </label>
        <input
          id="busca-registros"
          type="search"
          value={rascunho}
          placeholder="Buscar nos registros"
          // `search` já vem com um "x" nativo no Chrome e no Safari, que limpa o
          // campo disparando `change` — e o efeito acima cuida do resto.
          onChange={(evento) => setRascunho(evento.target.value)}
          onKeyDown={(evento) => {
            // Enter promove na hora, sem esperar o debounce: quem terminou de
            // digitar e apertou Enter já decidiu.
            if (evento.key === "Enter") {
              evento.preventDefault();
              onBuscar(rascunho);
            }
            // Esc limpa, como num campo de busca de qualquer lugar.
            if (evento.key === "Escape") {
              setRascunho("");
              onBuscar("");
            }
          }}
        />
      </div>
    </search>
  );
}
