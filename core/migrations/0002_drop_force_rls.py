"""
Desliga `FORCE ROW LEVEL SECURITY` (mantém `ENABLE`).

A 0001 ligou o FORCE seguindo o plano. Está errado para a topologia que este
projeto documenta, e o erro só apareceria em produção.

O que o FORCE faz: aplica as policies também ao **dono** da tabela. Em
desenvolvimento isso é inócuo, porque o dono é o `POSTGRES_USER`, que é
superusuário — e superusuário ignora RLS de qualquer jeito. Em produção, onde o
dono NÃO deve ser superusuário, o FORCE passa a valer, e aí:

- o Django Admin, que consulta como dono e nunca entra em `remind_app`, lista
  zero linhas em `tables`, `records`, `alert_rules` e `alerts`;
- apagar um usuário falha: o Django coleta os filhos em cascata com SELECTs que
  não enxergam nada, e o DELETE do pai bate na FK;
- uma data migration futura roda contra zero linhas e reporta sucesso.

Nada disso avisa. São três falhas silenciosas em troca de proteger o dono contra
si mesmo — e o dono, aqui, é infraestrutura de confiança: DDL, Admin e a criação
do banco de teste. Quem executa consulta de usuário é `remind_app`, que **não é
dono** e por isso continua sujeito às policies com ou sem FORCE.

Verificado neste cluster antes de mudar (tabela temporária, dono NOSUPERUSER
NOBYPASSRLS, uma linha que a policy não casa):

    RLS sem FORCE ..... o dono vê 1
    RLS com FORCE ..... o dono vê 0

A garantia de isolamento do runtime não muda: `core/tests/test_rls.py` confere
que o papel ativo durante uma request não é superusuário nem tem BYPASSRLS.
"""

from django.db import migrations

TABLES = ("tables", "columns", "records", "alert_rules", "alerts")

DROP_FORCE = "".join(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY;\n" for t in TABLES)
RESTORE_FORCE = "".join(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;\n" for t in TABLES)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_rls_policies")]

    operations = [migrations.RunSQL(sql=DROP_FORCE, reverse_sql=RESTORE_FORCE)]
