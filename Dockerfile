FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # pip valida TLS contra o bundle embutido do certifi, que ignora o trust store
    # do sistema. Apontar para o store do SO faz ele enxergar as CAs adicionadas
    # abaixo — necessário atrás de proxy/antivírus com inspeção TLS.
    # A verificação continua LIGADA; só a lista de raízes confiáveis muda.
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# CAs locais opcionais. Vazio na maioria das máquinas — ver docker/certs/README.md.
COPY docker/certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

COPY requirements/ requirements/
RUN pip install --upgrade pip && pip install -r requirements/dev.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
