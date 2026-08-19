from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from accounts.managers import UserManager
from accounts.validators import validate_timezone
from core.models import TimeStampedUUIDModel


class User(AbstractBaseUser, PermissionsMixin, TimeStampedUUIDModel):
    """
    Usuário identificado por e-mail, com UUID como chave primária.

    `TimeStampedUUIDModel` traz `id` (UUID), `created_at` e `updated_at`.
    `AbstractBaseUser` traz `password` e `last_login`; `PermissionsMixin` traz
    `is_superuser`, `groups` e `user_permissions`.
    """

    # db_collation com collation não-determinística no lugar de CITextField:
    # as classes CI* do django.contrib.postgres foram removidas no Django 5.1.
    # A collation `case_insensitive` é criada na migration 0001.
    # Efeito: UNIQUE passa a ser case-insensitive no próprio banco — não dá para
    # cadastrar Ana@x.com e ana@x.com nem inserindo direto no Postgres.
    email = models.EmailField(
        "e-mail",
        unique=True,
        max_length=254,
        db_collation="case_insensitive",
    )
    name = models.CharField("nome", max_length=120, blank=True)

    # Define o que é "hoje" para status de vencimento (RF10) e alertas (RF12).
    timezone = models.CharField(
        "fuso horário",
        max_length=64,
        default="America/Sao_Paulo",
        validators=[validate_timezone],
    )

    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("membro da equipe", default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.email

    def get_short_name(self) -> str:
        return self.name or self.email.split("@")[0]

    def get_full_name(self) -> str:
        return self.name or self.email
