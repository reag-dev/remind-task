import uuid

from django.db import models


class TimeStampedUUIDModel(models.Model):
    """
    Base de todos os models de domínio.

    UUID como chave primária (RS04): o identificador é público — aparece na URL —
    e um inteiro sequencial permitiria enumerar recursos alheios mesmo que a
    checagem de autorização falhasse. uuid4 é aleatório, não enumerável.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
