from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """Manager de User sem `username` — a identidade é o e-mail."""

    use_in_migrations = True

    def _create_user(self, email, name, password, **extra_fields):
        if not email:
            raise ValueError("E-mail é obrigatório.")
        if not password:
            raise ValueError("Senha é obrigatória.")

        # normalize_email() do Django só normaliza o domínio. Baixamos a string
        # inteira: a coluna já usa collation case-insensitive, mas normalizar na
        # escrita evita depender só do banco e mantém o dado canônico.
        email = self.normalize_email(email).lower()

        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, name="", password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, name, password, **extra_fields)

    def create_superuser(self, email, name="", password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa de is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa de is_superuser=True.")

        return self._create_user(email, name, password, **extra_fields)
