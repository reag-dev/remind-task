"""
Policy de RLS na tabela `users` (Phase 11).

Por que ela não existia até agora
---------------------------------
As policies da 0001 cobrem `tables`, `records`, `alert_rules`, `alerts` e
`columns` — as tabelas de domínio. `users` ficou de fora, e a omissão era
inofensiva enquanto nenhum endpoint apagava usuário: o `MeView` opera sobre
`request.user`, que vem do token, e o papel `remind_app` só lia a própria linha
porque nunca pediu outra.

`DELETE /api/auth/me/` muda isso. Apagar uma conta é a operação mais destrutiva
do sistema, e sem esta policy ela seria a única sem a segunda barreira — a
camada de queryset viraria a defesa única, que é exatamente a situação que
`tests/security/test_queryset_layer.py` foi escrito para impedir.

Por que ela não quebra o login
------------------------------
Esta é a pergunta que fez a policy parecer inviável quando o plano a registrou,
e a resposta está em `core/rls.py`: o rebaixamento para `remind_app` acontece
nas CLASSES DE AUTENTICAÇÃO do DRF, depois de `super().authenticate()` ter
resolvido o usuário. Ou seja:

- O SELECT que o JWT faz para achar o dono do token roda como **dono**, antes do
  `enter()`. A policy não se aplica.
- Login e registro são `AllowAny` e não passam por classe de autenticação
  nenhuma — nunca entram no papel. A policy não se aplica.
- O Admin autentica por sessão, fora do DRF, e continua consultando como dono.

O que fica sob a policy é o que roda DEPOIS da autenticação, em nome de um
usuário conhecido: e aí `id = app.user_id` é exatamente a regra desejada.

Sem `FORCE`, pelo mesmo motivo da 0002
--------------------------------------
O dono das tabelas é infraestrutura de confiança (DDL, Admin, criação do banco
de teste). Com FORCE, o Admin listaria zero usuários e uma data migration futura
rodaria contra zero linhas reportando sucesso. Quem executa consulta de usuário
no runtime é `remind_app`, que **não é dono** e por isso continua sujeito às
policies com ou sem FORCE.

Um detalhe que o job de alertas exige
-------------------------------------
`alerts.tasks.send_pending_email` roda dentro de `rls.session(user_id)` e faz
`select_related("user")` — um JOIN em `users`. A policy permite, porque a linha
juntada é a do próprio dono do alerta. Já `scan_due_records` percorre TODOS os
usuários, e por isso consulta a lista **fora** da sessão de RLS, como dono. As
duas coisas continuam funcionando, e é o que `core/tests/test_rls.py` confere.
"""

from django.db import migrations

# Mesma expressão das policies da 0001: GUC ausente ou vazia vira NULL, e
# `id = NULL` não casa com linha nenhuma. Fechado por default.
CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"

ENABLE = f"""
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_self ON users
    USING (id = {CURRENT_USER})
    WITH CHECK (id = {CURRENT_USER});
"""

DISABLE = """
DROP POLICY IF EXISTS users_self ON users;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0002_drop_force_rls")]

    operations = [migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE)]
