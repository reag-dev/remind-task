from django.db import transaction
from django.urls import path

from accounts import views

app_name = "accounts"

# O login roda FORA do ATOMIC_REQUESTS. Motivo, que não é óbvio:
#
#   ATOMIC_REQUESTS=True envolve a request inteira numa transação. Quando o DRF
#   trata uma APIException — o 401 de senha errada, por exemplo — o
#   exception_handler chama set_rollback(), revertendo tudo o que a request
#   escreveu. Inclusive o AccessAttempt que o django-axes acabou de gravar.
#   Efeito líquido: o contador de falhas nunca passa de zero e a proteção contra
#   força bruta fica inerte, silenciosamente.
#
# Este endpoint não perde nada com isso: é pré-autenticação, então não há
# `app.user_id` para o SET LOCAL da RLS (Phase 7), e as únicas escritas são o
# registro de tentativa do axes e o last_login — nenhuma precisa de atomicidade
# conjunta. Coberto por test_failed_login_attempt_survives_the_request.
login_view = transaction.non_atomic_requests(views.LoginView.as_view())

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", login_view, name="login"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    # Os dois nomes espelham o par pedir/consumir. O link do e-mail aponta para
    # a SPA, nao para estes endpoints — quem renderiza o formulario e o
    # frontend, que so entao chama o `confirm`.
    path(
        "password-reset/",
        views.PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]
