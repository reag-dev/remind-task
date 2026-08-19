# Sistema de Alertas e Tabelas Dinâmicas — Especificação

> Documento original do projeto, transcrito para o repositório na Phase 0.
> Fonte da verdade dos requisitos RF01–RF13 e RS01–RS08.

## 1. Visão geral

O **Sistema de Alertas** é uma aplicação para criação e gerenciamento de tabelas dinâmicas, permitindo que cada usuário registre informações estruturadas e associe datas de vencimento aos registros.

O principal objetivo é facilitar o acompanhamento de prazos e emitir notificações quando uma determinada data for atingida, mantendo como requisito fundamental a **proteção das informações armazenadas**, especialmente quando houver dados sensíveis.

A aplicação deve oferecer uma experiência simples para criação e gerenciamento das tabelas, com indicadores visuais de vencimento, ordenação automática por proximidade da data e possibilidade de exportação dos dados.

## 2. Objetivos

- Permitir que usuários criem suas próprias tabelas.
- Garantir que cada tabela pertença exclusivamente ao usuário que a criou.
- Permitir o cadastro, edição e exclusão de registros.
- Permitir a definição de uma data de vencimento para os registros.
- Emitir notificações relacionadas aos vencimentos.
- Destacar visualmente registros próximos ou atrasados.
- Ordenar os registros de acordo com o próximo vencimento.
- Permitir a exportação das tabelas em formato CSV.
- Priorizar segurança, privacidade e proteção dos dados armazenados.

## 3. Requisitos funcionais

| ID | Requisito | Onde é implementado |
|---|---|---|
| RF01 | Cadastro de usuário | `accounts` — Phase 1 |
| RF02 | Autenticação (login/logout) | `accounts` — Phase 1 |
| RF03 | Criação de tabela, com propriedade exclusiva do criador | `tables` — Phase 2 |
| RF04 | Visualização das tabelas da própria conta | `tables` — Phase 2 |
| RF05 | Estrutura dinâmica (colunas configuráveis) | `tables` — Phase 2 |
| RF06 | Campo de vencimento | `tables` (`column_type='due_date'`) — Phase 2 |
| RF07 | Inserção de registros | `records` — Phase 3 |
| RF08 | Edição de registros | `records` — Phase 3 |
| RF09 | Exclusão de registros | `records` — Phase 3 |
| RF10 | Indicadores de vencimento | `records` (anotação de status) — Phase 4 |
| RF11 | Ordenação por vencimento | `records` — Phase 4 |
| RF12 | Notificações | `alerts` — Phase 5 |
| RF13 | Exportação CSV | `exports` — Phase 6 |

### RF05 — tipos de coluna

Texto, número, data, booleano, e-mail, lista/opções, data de vencimento.
A implementação inicial pode limitar os tipos disponíveis e evoluir depois.

### RF10 — estados de vencimento

- **Vencido:** data já ultrapassada.
- **Vence hoje:** vencimento no dia atual.
- **Próximo do vencimento:** dentro de um período configurável.
- **Em dia:** vencimento ainda distante.

### RF11 — ordenação padrão

1. Vencidos
2. Vencendo hoje
3. Próximos vencimentos
4. Vencimentos futuros mais distantes

Deve ser possível alterar a ordenação manualmente.

### RF12 — evoluções previstas

Notificação in-app, e-mail, notificações programadas, diferentes níveis de antecedência.

## 4. Requisitos de segurança e privacidade

| ID | Requisito | Implementação |
|---|---|---|
| RS01 | Isolamento dos dados entre usuários | `get_queryset()` filtrado por `user` + RLS no Postgres (Phase 7) |
| RS02 | Autenticação **e** autorização por recurso | `permission_classes` + checagem de propriedade em toda view |
| RS03 | Proteção de credenciais | Argon2id via `argon2-cffi` (Phase 1) |
| RS04 | Proteção contra acesso indevido por troca de ID | UUID como identificador público + queryset filtrada por dono (404, não 403) |
| RS05 | Proteção de dados sensíveis | `columns.is_sensitive` + filtro de redação em logs, `DEBUG=False` (Phase 7) |
| RS06 | Comunicação segura | HTTPS obrigatório em produção (`config/settings/prod.py`) |
| RS07 | Controle de sessão | SimpleJWT com expiração, rotação e blacklist de refresh (Phase 1) |
| RS08 | Exportação segura | Export reutiliza a queryset autorizada + sanitização de CSV injection (Phase 6) |

### RS04 — o ataque a impedir

```text
GET /tables/123
```

Mesmo autenticado, a API deve verificar se a tabela `123` pertence ao requisitante antes de retornar os dados. A resposta para recurso alheio é **404**, nunca 403 — 403 confirmaria que o recurso existe.

## 5. Fluxos principais

### Cadastro
Usuário → cria conta → sistema valida → conta criada → login.

### Criação de tabela
Usuário autenticado → cria tabela → define nome e colunas → sistema associa ao usuário → tabela disponível.

### Cadastro de registro
Usuário → abre tabela → adiciona registro → define data de vencimento → sistema salva → registro aparece ordenado pela data.

### Processo de alerta
```text
Registro possui data de vencimento
          ↓
Sistema verifica a data
          ↓
Data atingiu condição de alerta?
     Não        Sim
      ↓          ↓
 Continua    Gera alerta
                ↓
          Usuário é notificado
```

O mecanismo deve evitar envio duplicado de notificações.

## 6. Modelo conceitual original

> Preservado para referência histórica. A modelagem **efetivamente adotada** está em
> [`data-model.md`](data-model.md) e diverge deliberadamente deste esboço: a entidade
> `RecordValue` (EAV) foi substituída por `records.data JSONB` + `records.due_date`.

**User:** `id`, `name`, `email`, `password_hash`, `created_at`, `updated_at`
**Table:** `id`, `user_id`, `name`, `created_at`, `updated_at`
**Column:** `id`, `table_id`, `name`, `type`, `position`, `is_required`, `created_at`, `updated_at`
**Record:** `id`, `table_id`, `created_at`, `updated_at`
**RecordValue:** `id`, `record_id`, `column_id`, `value`
**Alert:** `id`, `record_id`, `trigger_date`, `status`, `notified_at`, `created_at`

## 7. Exemplo de utilização

Tabela **Contratos**:

| Cliente | Contrato | Responsável | Data de vencimento | Status |
|---|---|---|---|---|
| Empresa A | CT-001 | João | 20/08/2026 | Ativo |
| Empresa B | CT-002 | Maria | 25/08/2026 | Ativo |
| Empresa C | CT-003 | Pedro | 15/08/2026 | Vencido |

Apresentação priorizada: Empresa C (vencido) → Empresa A (vence em breve) → Empresa B (futuro).

## 8. Escopo do MVP

### Essencial
Cadastro de usuário · login/logout · criação e exclusão de tabela · definição de colunas · tipos básicos de coluna · CRUD de registros · campo de data de vencimento · ordenação por vencimento · indicadores visuais · notificação in-app · exportação CSV · controle de acesso por usuário · proteção dos dados armazenados.

### Futuro
Notificação por e-mail · configuração de antecedência do alerta · recorrência de vencimentos · compartilhamento de tabelas · níveis de permissão · histórico de alterações · auditoria · importação de CSV · filtros avançados · pesquisa global · templates de tabelas · criptografia adicional para campos sensíveis.

## 9. Arquitetura sugerida

```text
Frontend → API/Backend → Autenticação + Autorização → Banco de dados → Serviço de processamento de alertas
```

O processamento de alertas roda em job/worker periódico:

```text
A cada X minutos → busca registros próximos do vencimento → verifica se o alerta já foi enviado
→ gera a notificação → registra que o alerta foi processado
```

## 10. Critérios de segurança do MVP

Validados pela suite da Phase 8 (`tests/security/`):

- [ ] Usuário A não consegue acessar tabelas do usuário B.
- [ ] Usuário A não consegue editar registros do usuário B.
- [ ] Usuário A não consegue excluir registros do usuário B.
- [ ] Endpoints protegidos exigem autenticação.
- [ ] Senhas não são armazenadas em texto puro.
- [ ] Dados trafegam via HTTPS em produção.
- [ ] Dados sensíveis não aparecem em logs desnecessariamente.
- [ ] Exportação CSV exige autenticação e autorização.
- [ ] Tentativas de acesso indevido são tratadas de forma segura.
- [ ] Alertas não expõem informações sensíveis desnecessariamente.

## 11. Diferencial

**Flexibilidade + Controle de vencimentos + Alertas + Privacidade.**

Ferramenta simples para quem precisa armazenar informações estruturadas e, principalmente, **não pode esquecer de uma data importante**. Segurança é parte central da arquitetura, não funcionalidade adicionada depois.

## 12. Casos de uso

Contratos · documentos · renovação de certificados · licenças · garantias · vencimento de serviços · documentos empresariais · prazos internos · assinaturas · manutenções · validade de informações cadastrais.

## 13. Visão de produto

> Uma plataforma privada para criação de tabelas personalizadas, gerenciamento de registros e acompanhamento inteligente de vencimentos, com alertas automáticos e foco em segurança e proteção dos dados.
