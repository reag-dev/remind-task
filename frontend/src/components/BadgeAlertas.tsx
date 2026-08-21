import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { listarAlertas } from "../api/alerts.ts";
import { chaves } from "../api/query.ts";

/**
 * Só a contagem interessa, então pede-se uma linha.
 *
 * `page_size=1` traz o `count` do envelope sem trafegar 50 registros que
 * ninguém vai ler. Isso só é possível porque a `PaginacaoPadrao` da Phase 5
 * expõe o parâmetro — com o padrão do DRF, cada atualização do contador
 * baixaria a primeira página inteira.
 */
const CONSULTA = { status: "sent", page_size: 1 } as const;

/** Cinco minutos. O job roda uma vez por dia; polling curto seria desperdício. */
const INTERVALO = 5 * 60 * 1000;

export function BadgeAlertas() {
  const alertas = useQuery({
    queryKey: chaves.alertasCom(CONSULTA),
    queryFn: () => listarAlertas(CONSULTA),
    refetchInterval: INTERVALO,
    // Sem WebSocket de propósito: a granularidade da informação é o dia, e um
    // canal permanente aberto para atualizar um número seria custo sem retorno.
    refetchOnWindowFocus: true,
  });

  const total = alertas.data?.count ?? 0;

  return (
    <Link to="/alertas" className="link-alertas">
      Alertas
      {total > 0 && (
        // O número entra no texto acessível do link, e não só numa bolinha
        // colorida: quem usa leitor de tela ouviria apenas "Alertas" e não
        // saberia que há algo esperando.
        <span className="badge" aria-label={`${total} não lido${total === 1 ? "" : "s"}`}>
          {total > 99 ? "99+" : total}
        </span>
      )}
    </Link>
  );
}
