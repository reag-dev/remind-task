import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from alerts.emails import enviar
from alerts.models import Alert, AlertChannel, AlertRule, AlertStatus
from alerts.services import generate_for_user
from core import rls
from core.dates import today_in

logger = logging.getLogger(__name__)


@shared_task(name="alerts.scan_due_records")
def scan_due_records() -> int:
    """
    Varre os vencimentos e emite os alertas devidos (RF12).

    Percorre usuário a usuário, e não numa varredura global, porque "hoje"
    depende do fuso de cada um: às 02:00 UTC já é dia seguinte em Tóquio e ainda
    é o dia anterior em São Paulo. Uma varredura única usaria a data do servidor
    e erraria o disparo por até um dia inteiro para boa parte dos usuários.

    Seguro para repetir: a unicidade (record, rule, trigger_date) impede
    duplicata mesmo com execuções sobrepostas ou retry da task.
    """
    User = get_user_model()

    # Só quem tem regra ativa — evita percorrer a base inteira a cada 15 minutos.
    candidates = User.objects.filter(
        is_active=True,
        id__in=AlertRule.objects.filter(is_active=True).values("user_id"),
    ).only("id", "timezone")

    total = 0
    for user in candidates.iterator(chunk_size=500):
        try:
            # RS01 — uma transação por usuário. O job roda fora de qualquer
            # request, então é aqui que ele entra no papel `remind_app`; o
            # COMMIT desfaz papel e GUC, e o usuário seguinte começa limpo.
            with rls.session(user.pk):
                created = generate_for_user(user, today_in(user.timezone))
        except Exception:
            # Um usuário com dado estranho não pode derrubar a varredura dos
            # demais. Sem e-mail, id ou payload no log (RS05).
            logger.exception("Falha ao gerar alertas para o usuário %s", user.pk)
            continue

        if created:
            logger.info("Alertas gerados: %s (usuário %s)", created, user.pk)
            total += created

    return total


# ------------------------------------------------------------------ entrega


def _espera_cumprida(alert, agora) -> bool:
    """
    O backoff exponencial entre tentativas.

    Sem isto, o cron a cada 15 minutos viraria uma rajada contra um provedor que
    já está caído — que é exatamente quando ele menos aguenta. A espera dobra a
    cada tentativa: 2, 4, 8, 16 minutos.

    A conta é feita aqui e não no SQL de propósito: o intervalo depende do
    número de tentativas DAQUELA linha, e a expressão condicional que isso exige
    no banco custaria mais em legibilidade do que economiza — o conjunto de
    pendentes é pequeno por construção.
    """
    if alert.last_attempt_at is None:
        return True

    minutos = settings.EMAIL_RETRY_BASE_MINUTES * (2 ** (alert.delivery_attempts - 1))
    return agora - alert.last_attempt_at >= timedelta(minutes=minutos)


def _entregar(user_id, alert_id) -> str:
    """
    Tenta entregar UM alerta. Devolve o desfecho: `enviado`, `falhou` ou `adiado`.

    A trava contra e-mail duplicado é o `select_for_update` combinado com o
    filtro `status=PENDING` relido DENTRO da transação. Ler antes e gravar
    depois não serve: dois workers leriam PENDING ao mesmo tempo e o usuário
    receberia o mesmo aviso duas vezes. `skip_locked` faz o segundo seguir
    adiante em vez de esperar por uma linha que já está sendo entregue.

    O envio acontece dentro da transação, com a linha travada, e isso é escolha
    consciente: segurar um lock durante I/O de rede é feio, mas é o que garante
    que ninguém mais pegue esta linha enquanto o SMTP responde. O custo fica
    limitado por `EMAIL_TIMEOUT` — sem ele, a linha ficaria travada pelo timeout
    do sistema operacional, que passa de dois minutos.

    Roda dentro de `rls.session` porque a task não tem request: é aqui que a
    conexão entra no papel `remind_app` em nome do dono do alerta.
    """
    with rls.session(user_id):
        alert = (
            Alert.objects.select_for_update(skip_locked=True)
            .select_related("record", "record__table", "user")
            # As colunas alimentam o rótulo seguro (RS05); sem o prefetch cada
            # e-mail faria a própria consulta.
            .prefetch_related("record__table__columns")
            .filter(pk=alert_id, status=AlertStatus.PENDING)
            .first()
        )

        # Sumiu de PENDING ou está travado por outro worker. As duas situações
        # significam a mesma coisa aqui: não é nossa para entregar.
        if alert is None:
            return "adiado"

        agora = timezone.now()
        if not _espera_cumprida(alert, agora):
            return "adiado"

        alert.delivery_attempts += 1
        alert.last_attempt_at = agora
        campos = ["delivery_attempts", "last_attempt_at", "status", "updated_at"]

        try:
            enviar(alert)
        except Exception:
            # Sem endereço, assunto ou corpo no log (RS05) — o RedactingFilter
            # cobre o `data`, mas o destinatário não passa por ele.
            logger.exception(
                "Falha ao entregar o alerta %s (tentativa %s)",
                alert.pk,
                alert.delivery_attempts,
            )

            # Só desiste no limite. Continuar PENDING é o que faz a próxima
            # execução tentar de novo; FAILED é definitivo e tira da fila.
            if alert.delivery_attempts >= settings.EMAIL_MAX_ATTEMPTS:
                alert.status = AlertStatus.FAILED
            alert.save(update_fields=campos)
            return "falhou"

        alert.status = AlertStatus.SENT
        alert.notified_at = agora
        alert.save(update_fields=[*campos, "notified_at"])
        return "enviado"


@shared_task(name="alerts.send_pending_emails")
def send_pending_emails() -> dict[str, int]:
    """
    Entrega os alertas de e-mail pendentes (RF12).

    Separada de `scan_due_records` de propósito: gerar e entregar falham por
    motivos diferentes — um dado estranho numa tabela versus um provedor fora do
    ar — e uma não pode levar a outra junto.

    Seguro para repetir. Um alerta só sai de PENDING quando a entrega confirma,
    e a corrida entre execuções sobrepostas é resolvida em `_entregar`.
    """
    # Esta consulta roda FORA do RLS, como o dono das tabelas — igual à varredura
    # de `scan_due_records`, que também precisa enxergar todos os usuários para
    # depois entrar no contexto de cada um. A entrega em si já é por usuário.
    candidatos = list(
        Alert.objects.filter(
            status=AlertStatus.PENDING,
            rule__channel=AlertChannel.EMAIL,
            # Conta desativada não recebe aviso. Sem isto, desativar um usuário
            # não pararia o e-mail — só o login.
            user__is_active=True,
            delivery_attempts__lt=settings.EMAIL_MAX_ATTEMPTS,
        )
        .order_by("trigger_date")
        .values_list("user_id", "id")
    )

    desfechos = {"enviados": 0, "falhos": 0, "adiados": 0}
    contador = {"enviado": "enviados", "falhou": "falhos", "adiado": "adiados"}

    for user_id, alert_id in candidatos:
        try:
            desfechos[contador[_entregar(user_id, alert_id)]] += 1
        except Exception:
            # Um alerta problemático não pode parar a fila dos demais — mesma
            # regra que a varredura aplica por usuário.
            logger.exception("Erro inesperado ao processar o alerta %s", alert_id)
            desfechos["falhos"] += 1

    if desfechos["enviados"] or desfechos["falhos"]:
        logger.info("Entrega de e-mail: %s", desfechos)

    return desfechos
