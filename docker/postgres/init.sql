-- Extensões exigidas pelo modelo de dados.
--   citext   -> users.email case-insensitive com UNIQUE nativo
--   pgcrypto -> gen_random_uuid() (nativo no PG13+, mantido por compatibilidade)
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
