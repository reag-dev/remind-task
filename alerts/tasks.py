import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef

from alerts.models import AlertRule
from alerts.services import generate_for_user
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
