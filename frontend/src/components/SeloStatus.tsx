import { ROTULO_DUE_STATUS, ehDueStatus } from "../api/tipos.ts";
import { textoDeDias } from "../formato.ts";

/**
 * Indicador de vencimento (RF10).
 *
 * O valor vem pronto de `record.due_status`. **Não se recalcula aqui**, e nem a
 * partir de `days_until_due`: a regra já tem três implementações no backend
 * (Python em `due_status_for`, SQL em `with_due_status`, e predicado de faixa
 * em `status_filter_q`), todas amarradas entre si por
 * `test_sql_and_python_agree_on_every_status`. Uma quarta em TypeScript não
 * teria quem a cobrasse e sairia de sincronia justamente no que o usuário vê.
 *
 * Cor não é indicador sozinha. Cada selo carrega o texto do estado, porque
 * daltonismo é comum e "indicadores visuais" que só mudam de cor não informam
 * parte do público.
 */
export function SeloStatus({ status, dias }: { status: string; dias: number | null }) {
  if (!ehDueStatus(status)) {
    // O schema declara `due_status` como `string`, não como união — o backend
    // pode acrescentar um estado sem quebrar a compilação aqui. Melhor mostrar
    // o valor cru do que uma célula vazia sem explicação.
    return <span className="selo selo-desconhecido">{status}</span>;
  }

  return (
    <span className={`selo selo-${status}`}>
      {ROTULO_DUE_STATUS[status]}
      {dias !== null && status !== "no_due" && (
        <span className="sutil"> · {textoDeDias(dias)}</span>
      )}
    </span>
  );
}
