from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.cookies import (
    delete_refresh_cookie,
    read_refresh_token,
    set_refresh_cookie,
)
from accounts.serializers import (
    AccessTokenSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


@extend_schema(tags=["auth"], summary="Cadastro de usuário (RF01)")
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


@extend_schema(
    tags=["auth"],
    summary="Login (RF02)",
    description=(
        "Retorna o access token no corpo e grava o refresh token em cookie "
        "httpOnly. Apos 5 falhas na combinacao IP+usuario, django-axes responde 429."
    ),
)
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh = response.data.pop("refresh", None)
        if refresh:
            set_refresh_cookie(response, refresh)
        return response


@extend_schema(
    tags=["auth"],
    summary="Renova o access token",
    description=(
        "Lê o refresh do cookie httpOnly (ou do corpo). Com rotação ativa, o "
        "token antigo vai para a blacklist e um novo é gravado no cookie."
    ),
    request=None,
    responses={200: AccessTokenSerializer},
)
class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw = read_refresh_token(request)
        if not raw:
            return Response(
                {"detail": "Refresh token ausente."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        data = dict(serializer.validated_data)
        rotated = data.pop("refresh", None)

        response = Response(data)
        if rotated:
            set_refresh_cookie(response, rotated)
        return response


@extend_schema(
    tags=["auth"],
    summary="Logout (RF02)",
    description=(
        "Coloca o refresh token na blacklist e apaga o cookie. Idempotente: "
        "token já inválido também resulta em 204."
    ),
    request=None,
    responses={204: OpenApiResponse(description="Sessão encerrada.")},
)
class LogoutView(APIView):
    # AllowAny de propósito: encerrar a sessão precisa funcionar mesmo com o
    # access token já expirado. A autoridade aqui é a posse do refresh token.
    permission_classes = [AllowAny]

    def post(self, request):
        raw = read_refresh_token(request)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                # Já expirado, já na blacklist ou malformado — o efeito desejado
                # (token não vale mais) já está satisfeito.
                pass

        response = Response(status=status.HTTP_204_NO_CONTENT)
        return delete_refresh_cookie(response)


@extend_schema(tags=["auth"], summary="Dados da conta autenticada")
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Nunca resolve por id vindo da URL — o recurso é sempre o requisitante.
        return self.request.user
