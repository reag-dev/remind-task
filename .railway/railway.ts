/**
 * Infraestrutura do remind-task no Railway.
 *
 * ESTE ARQUIVO NÃO É `railway.toml`, e a diferença tem data: o Config as Code
 * (`railway.toml` / `railway.json`) foi descontinuado e o Railway para de lê-lo
 * em 2026-12-01. O substituto é Infrastructure as Code — este arquivo. Escrever
 * o `.toml` que a Phase 3 do plano pedia daria três meses de vida útil.
 *
 * ⚠️ ANTES DO PRIMEIRO DEPLOY:
 *
 *     railway run --service web python manage.py preflight_db
 *
 * A migration de RLS faz `CREATE ROLE`. Se o banco não permitir, ela falha no
 * MEIO da sequência e deixa o schema pela metade — bem pior do que não começar.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * O QUE NÃO ESTÁ AQUI, E POR QUÊ
 *
 * A referência de IaC documenta, para `service()`, apenas: `source`, `build`
 * (string), `start`, `healthcheck`, `healthcheckTimeout`, `replicas`, `env`,
 * `volumeMounts` e `domains`. Campos como `cronSchedule`, `restartPolicyType` e
 * `build` como objeto aparecem na referência do formato DEPRECADO, e não
 * consegui confirmá-los para o IaC nem na doc nem no SDK.
 *
 * Então eles não estão neste arquivo. O que precisa deles está listado no
 * README, em "Deploy no Railway", como ajuste de painel. Escrever campo não
 * confirmado aqui daria um arquivo que parece completo e falha na aplicação —
 * ou, pior, é aceito e ignorado em silêncio.
 * ────────────────────────────────────────────────────────────────────────────
 */

import {
  defineRailway,
  github,
  postgres,
  preserve,
  project,
  redis,
  service,
} from "railway/iac";

const REPO = "reag-dev/remind-task";
const BRANCH = "main";

export default defineRailway(() => {
  const db = postgres("postgres");
  const cache = redis("redis");

  /**
   * Variáveis comuns aos três serviços Python.
   *
   * `preserve()` em tudo que é segredo ou específico do ambiente: o valor real
   * vive no painel e este arquivo nunca o vê. Sem isso, um deploy sobrescreveria
   * a SECRET_KEY de produção pelo que estivesse escrito aqui — que é como se
   * invalida toda sessão ativa sem querer.
   */
  const comuns = {
    DJANGO_SETTINGS_MODULE: "config.settings.prod",
    DJANGO_SECRET_KEY: preserve(),
    DATABASE_URL: db.env.DATABASE_URL,
    REDIS_URL: cache.env.REDIS_URL,
    // Banco 1: o 0 é do Celery. Ver a nota de CACHES em config/settings/base.py
    // — os contadores de throttle precisam ser compartilhados entre os workers.
    CACHE_URL: preserve(),
  };

  const web = service("web", {
    source: github(REPO, { branch: BRANCH }),
    // Sem `start`: o Dockerfile da raiz termina em
    // CMD ["/app/docker/entrypoint.sh"], que migra e faz exec do gunicorn na
    // $PORT. Repetir o comando aqui criaria um segundo lugar para esquecer de
    // atualizar — e o entrypoint é o caminho que o CI já exercita.
    // ⚠️ O healthcheck NÃO chega pelo domínio público: a plataforma alcança o
    // container pela rede interna, em HTTP puro e com `Host:
    // healthcheck.railway.app`. Isso derrubou o primeiro deploy real
    // (2026-08-24) por dois motivos ao mesmo tempo — 400 por DisallowedHost e
    // 301 por SECURE_SSL_REDIRECT —, e deploy reprovado nunca entra em serviço:
    // o domínio devolve 502 com o container de pé.
    //
    // O que faz isto funcionar hoje: o host do healthcheck entra em
    // ALLOWED_HOSTS quando RAILWAY_PUBLIC_DOMAIN existe (base.py), e
    // `/api/health/` está em SECURE_REDIRECT_EXEMPT (prod.py). Mexer em
    // qualquer um dos dois traz o 502 de volta.
    healthcheck: "/api/health/",
    healthcheckTimeout: 60,
    env: {
      ...comuns,
      // Estas três são do `web` e só dele: são a configuração da superfície
      // HTTP, e é o carregamento do WSGI que as valida (config/validacao.py).
      //
      // Elas chegaram a ficar no bloco comum, depois que o worker quebrou por
      // falta delas no primeiro deploy real (2026-08-24). Aquilo era remendo:
      // exigir uma lista de origens CORS de um processo que não atende
      // requisição só adiava a próxima guarda a derrubá-lo. A causa foi
      // corrigida onde estava.
      DJANGO_ALLOWED_HOSTS: preserve(),
      // Origem EXATA do frontend, com esquema. Obrigatória: `prod.py` levanta
      // ImproperlyConfigured se vier vazia, porque com SameSite=None e o front
      // em outro registrable domain, CORS vazio significa SPA em branco.
      CORS_ALLOWED_ORIGINS: preserve(),
      CSRF_TRUSTED_ORIGINS: preserve(),
    },
  });

  const worker = service("worker", {
    source: github(REPO, { branch: BRANCH }),
    start: "celery -A config worker -l info",
    // Sem healthcheck de propósito: o worker não escuta em porta nenhuma, e um
    // healthcheck aqui reiniciaria um processo saudável em laço.
    env: comuns,
  });

  /**
   * A varredura de alertas.
   *
   * O plano questionou o serviço `beat`, com razão: é um processo ocioso 24
   * horas por dia para disparar UMA task a cada 15 minutos, e o Railway cobra
   * por serviço de pé. A escolha é de custo, não de correção — a constraint
   * `alerts_idempotency` sobre `(record, rule, trigger_date)` já impede
   * duplicata mesmo com execuções sobrepostas.
   *
   * ⚠️ O `cronSchedule` (`*/15 * * * *`) precisa ser ligado NO PAINEL — ver o
   * bloco no topo deste arquivo. Enquanto não for, este serviço roda a varredura
   * uma vez e sai, e nada reagenda.
   *
   * Para voltar ao beat: trocar o `start` por `celery -A config beat -l info` e
   * limpar o cron. O `CELERY_BEAT_SCHEDULE` continua em base.py, intacto.
   */
  const cron = service("cron-alertas", {
    source: github(REPO, { branch: BRANCH }),
    start: "python manage.py scan_alerts",
    env: comuns,
  });

  /**
   * O frontend é uma imagem ESPECÍFICA DO AMBIENTE, e isso não é detalhe.
   *
   * O Vite resolve `import.meta.env` em tempo de COMPILAÇÃO, então a URL da API
   * fica embutida no bundle: não existe "promover a mesma imagem de staging para
   * produção", ela sairia falando com a API errada. O build falha de propósito
   * se `VITE_API_URL` não vier — e as variáveis do serviço chegam ao build como
   * ARG, que é como o `frontend/Dockerfile` a recebe.
   *
   * Não há `target` aqui, e não precisa: `producao` é o ÚLTIMO estágio do
   * arquivo, então um build sem alvo já produz a imagem de nginx. Foi por isso
   * que ele foi posto por último.
   */
  const frontend = service("frontend", {
    source: github(REPO, { branch: BRANCH }),
    healthcheck: "/",
    env: {
      // Caminho do Dockerfile por variável — é o mecanismo que o Railway
      // documenta para arquivo fora da raiz.
      RAILWAY_DOCKERFILE_PATH: "frontend/Dockerfile",
      // A URL PÚBLICA do serviço `web`, com `/api` no fim. Quem faz a
      // requisição é o browser, que não resolve nome interno do Railway.
      VITE_API_URL: preserve(),
    },
  });

  return project("remind-task", {
    resources: [db, cache, web, worker, cron, frontend],
  });
});
