from contextlib import suppress

from axes.utils import reset as axes_reset
from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts import emails
from accounts.cookies import (
    delete_refresh_cookie,
    read_refresh_token,
    set_refresh_cookie,
)
from accounts.serializers import (
    AccessTokenSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from core.throttling import RecuperacaoDeSenhaThrottle

User = get_user_model()


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
            # Já expirado, já na blacklist ou malformado — o efeito desejado
            # (token não vale mais) já está satisfeito.
            with suppress(TokenError):
                RefreshToken(raw).blacklist()

        response = Response(status=status.HTTP_204_NO_CONTENT)
        return delete_refresh_cookie(response)


@extend_schema(tags=["auth"], summary="Dados da conta autenticada")
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Nunca resolve por id vindo da URL — o recurso é sempre o requisitante.
        return self.request.user


@extend_schema(
    tags=["auth"],
    summary="Pede o link de redefinição de senha",
    description=(
        "Sempre 204, exista ou não a conta. A resposta é idêntica nos dois "
        "casos de propósito — ver a nota na view."
    ),
    request=PasswordResetRequestSerializer,
    responses={204: OpenApiResponse(description="Pedido recebido.")},
)
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    # Teto próprio, apertado: cada chamada faz o servidor mandar e-mail para um
    # endereço que QUEM CHAMA escolhe. Ver core/throttling.py.
    throttle_classes = [RecuperacaoDeSenhaThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # `filter().first()` e não `get()`: o caminho "não existe" não pode ser
        # uma exceção, porque exceção vira resposta diferente.
        #
        # `is_active=True` junto — conta desativada não recebe link. Sem isso,
        # desativar uma conta deixaria de ser suficiente para tirá-la do ar.
        user = User.objects.filter(
            email=serializer.validated_data["email"], is_active=True
        ).first()

        if user is not None:
            emails.enviar(user)

        # 204 SEMPRE. Um 404 para e-mail desconhecido transformaria o endpoint
        # num verificador de cadastro: bastaria varrer uma lista de endereços e
        # ler os códigos de resposta. É o mesmo raciocínio do RS04.
        #
        # ⚠️ O que esta simetria NÃO cobre: o TEMPO. Endereço com conta paga um
        # SMTP; endereço sem conta responde na hora. A diferença é medível por
        # quem insista, e some no ruído da rede para quem não. Fechá-la exigiria
        # empurrar o envio para a fila do Celery — o que troca um oráculo de
        # tempo por um modo de falha silencioso (worker fora do ar = ninguém
        # recupera senha, sem nada na resposta dizendo isso). A troca não vale a
        # pena aqui, e fica registrada em vez de esquecida.
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["auth"],
    summary="Redefine a senha com o token do e-mail",
    description=(
        "Consome o link. Em caso de sucesso, TODAS as sessões em aberto são "
        "encerradas e o bloqueio do django-axes é limpo."
    ),
    request=PasswordResetConfirmSerializer,
    responses={
        204: OpenApiResponse(description="Senha redefinida."),
        400: OpenApiResponse(description="Link inválido ou senha recusada."),
    },
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RecuperacaoDeSenhaThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])

        # O token morre aqui, sozinho: o PasswordResetTokenGenerator deriva o
        # hash da senha atual, e a senha acabou de mudar. Uso único sem tabela,
        # sem coluna e sem rotina de limpeza.

        _encerrar_sessoes(user)

        # Quem esqueceu a senha erra várias vezes ANTES de pedir o link — e com
        # AXES_FAILURE_LIMIT=5 chega ao fim do fluxo ainda bloqueado, com a senha
        # nova em mãos e um 403 na cara, sem entender por quê. Limpar aqui é o
        # que faz o fluxo terminar de verdade.
        axes_reset(username=user.email)

        return Response(status=status.HTTP_204_NO_CONTENT)


def _encerrar_sessoes(user) -> None:
    """
    Blacklist de todo refresh token em aberto do usuário (RS07).

    Sem isto, quem roubou um refresh continua dentro por 7 dias **justamente
    depois** de a vítima trocar a senha por suspeitar do roubo — que é o único
    momento em que ela acha que resolveu o problema. Trocar a senha sem cortar
    as sessões é dar uma sensação de segurança que não corresponde a nada.

    `get_or_create` porque um token já na blacklist (logout anterior) não é erro:
    o efeito desejado já está satisfeito.
    """
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)
