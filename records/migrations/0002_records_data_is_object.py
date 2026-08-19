from django.db import migrations

# `jsonb_typeof` não tem equivalente no ORM, então a constraint vai em SQL cru.
#
# O serializer já garante que `data` é um objeto, mas isto é a rede embaixo:
# um `Record.objects.update(data=[...])`, um script de importação ou um INSERT
# manual poderiam gravar um array ou um escalar no lugar. Todo o resto do
# sistema — validador, promoção de due_date, export CSV — assume um objeto.

FORWARD = """
ALTER TABLE records
    ADD CONSTRAINT records_data_is_object
    CHECK (jsonb_typeof(data) = 'object');
"""

BACKWARD = """
ALTER TABLE records
    DROP CONSTRAINT IF EXISTS records_data_is_object;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=BACKWARD),
    ]
