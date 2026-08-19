# CAs locais

Qualquer arquivo `*.crt` (formato PEM) aqui é instalado no trust store do container
durante o build, via `update-ca-certificates`.

**Para que serve:** antivírus e proxies corporativos que fazem inspeção TLS
(Avast, Kaspersky, ESET, Zscaler, Netskope…) reemitem os certificados de todo site
HTTPS com uma CA própria. O Windows confia nessa CA; o container Linux não. O
resultado é `pip install` morrendo com:

```
SSL: CERTIFICATE_VERIFY_FAILED - unable to get local issuer certificate
```

**A solução NÃO é `pip install --trusted-host`.** Isso desliga a verificação TLS e
abre a porta para pacote adulterado. O correto é ensinar o container a confiar na
mesma raiz que o host já confia — que é o que este diretório faz. A verificação
continua ligada.

## Como extrair a CA no Windows

| Produto | Caminho típico |
|---|---|
| Avast / AVG | `C:\ProgramData\Avast Software\Avast\wscert.pem` |
| Kaspersky | `C:\ProgramData\Kaspersky Lab\...\(fake)root.cer` |
| ESET | exportar via Certificados do Windows → `ESET SSL Filter CA` |
| Proxy corporativo | pedir ao time de TI |

```bash
cp "/c/ProgramData/Avast Software/Avast/wscert.pem" docker/certs/local-mitm-root.crt
docker compose build
```

Confirme qual CA está interceptando:

```bash
docker run --rm python:3.12-slim sh -c \
  "openssl s_client -connect pypi.org:443 -servername pypi.org </dev/null 2>/dev/null | grep -E '^ *i:'"
```

Se a linha `i:` mostrar uma CA pública real (Let's Encrypt, DigiCert…), não há
interceptação e este diretório pode ficar vazio.

## Por que os `.crt` não vão para o repositório

São específicos da máquina — a CA do Avast do seu notebook não serve para ninguém
mais, e commitar raízes de confiança em repositório é péssima higiene. O
`.gitignore` cobre `docker/certs/*.crt`.

## Alternativa

Desligar o "Web Shield / HTTPS scanning" do antivírus resolve na origem e dispensa
este diretório. É a opção mais limpa se você controla a máquina.
