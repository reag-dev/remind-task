from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Representação pública do usuário. Nunca inclui `password`."""

    class Meta:
        model = User
        fields = ("id", "email", "name", "timezone", "created_at")
        read_only_fields = ("id", "email", "created_at")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        trim_whitespace=False,  # espaço no início/fim é senha válida
    )

    class Meta:
        model = User
        fields = ("id", "email", "name", "timezone", "password")
        read_only_fields = ("id",)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate(self, attrs):
        # Roda os AUTH_PASSWORD_VALIDATORS com uma instância não salva, para que
        # o UserAttributeSimilarityValidator possa comparar a senha com e-mail e
        # nome. Passar user=None desligaria essa checagem em silêncio.
        candidate = User(email=attrs.get("email", ""), name=attrs.get("name", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            # Sem isso o erro cai em `non_field_errors` e o cliente não sabe qual
            # campo corrigir.
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class AccessTokenSerializer(serializers.Serializer):
    """Corpo de /auth/refresh/. O refresh rotacionado sai só no cookie."""

    access = serializers.CharField(read_only=True)


class LoginSerializer(TokenObtainPairSerializer):
    """Adiciona o usuário ao corpo da resposta de login."""

    def validate(self, attrs):
        # O SimpleJWT repassa `self.context["request"]` para authenticate(), e
        # aqui isso seria a Request do DRF. Dois problemas com o django-axes:
        #
        # 1. authenticate() do Django ENGOLE o PermissionDenied levantado pelo
        #    backend do axes e devolve None — o bloqueio viraria 401, não 403.
        # 2. O axes sinaliza o bloqueio com setattr(request, "axes_locked_out"),
        #    que cairia no wrapper do DRF. O AxesMiddleware inspeciona o
        #    HttpRequest de baixo e nunca enxergaria a marca.
        #
        # Passar o HttpRequest cru fecha os dois: o middleware vê a marca e troca
        # a resposta pelo 403 de lockout.
        request = self.context.get("request")
        if request is not None and hasattr(request, "_request"):
            self.context["request"] = request._request

        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
