import { useEffect, useRef } from "react";

type Props = {
  titulo: string;
  children: React.ReactNode;
  rotuloConfirmar: string;
  confirmando?: boolean;
  /**
   * Trava do botão de confirmar por uma condição do chamador.
   *
   * Separado de `confirmando` de propósito: os dois desabilitam o botão, mas
   * dizem coisas diferentes — `confirmando` troca o rótulo para "Excluindo…"
   * porque a ação está em curso, enquanto isto aqui significa "ainda não pode".
   * Reusar um pelo outro faria a tela anunciar uma exclusão que não começou.
   *
   * Nasceu da confirmação por digitação do e-mail (Phase 11).
   */
  confirmarDesabilitado?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
};

/**
 * Confirmação para ação destrutiva, sobre `<dialog>` nativo.
 *
 * O elemento nativo em vez de uma div com `position: fixed` porque ele já traz,
 * de graça e correto, o que costuma faltar numa modal escrita à mão: foco preso
 * dentro do diálogo, `Esc` fechando, o resto da página marcado como inerte para
 * leitor de tela, e o `::backdrop`.
 */
export function DialogoConfirmar({
  titulo,
  children,
  rotuloConfirmar,
  confirmando = false,
  confirmarDesabilitado = false,
  onConfirmar,
  onCancelar,
}: Props) {
  const referencia = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    // `showModal()` e não o atributo `open`: só ele ativa foco preso e backdrop.
    referencia.current?.showModal();
  }, []);

  return (
    <dialog
      ref={referencia}
      // `Esc` dispara `cancel` sem passar por nenhum botão. Sem tratar, o
      // diálogo fecharia no DOM e o estado do React continuaria achando que ele
      // está aberto — ele não reabriria mais.
      onCancel={(evento) => {
        evento.preventDefault();
        onCancelar();
      }}
      className="dialogo"
    >
      <h2>{titulo}</h2>
      {children}
      <div className="dialogo-acoes">
        <button type="button" className="secundario" onClick={onCancelar}>
          Cancelar
        </button>
        <button
          type="button"
          className="destrutivo"
          onClick={onConfirmar}
          disabled={confirmando || confirmarDesabilitado}
        >
          {confirmando ? "Excluindo…" : rotuloConfirmar}
        </button>
      </div>
    </dialog>
  );
}
