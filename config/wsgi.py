import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()

# Depois do `get_wsgi_application()`, que é quem chama `django.setup()` e deixa
# as settings prontas para leitura.
#
# Aqui, e não no corpo de `config/settings/prod.py`, porque este módulo é
# importado por quem VAI SERVIR HTTP — gunicorn e `runserver`, via
# WSGI_APPLICATION — e por mais ninguém. Validar dentro das settings fazia o
# worker do Celery, que não atende requisição, se recusar a subir por falta de
# uma lista de origens CORS. Ver config/validacao.py.
from config.validacao import validar_superficie_http  # noqa: E402

validar_superficie_http()
