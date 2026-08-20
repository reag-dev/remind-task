import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// Regras declaradas explicitamente, como o ruff.toml do backend. O conjunto
// "recomendado" de cada plugin muda entre versões menores, e uma regra que
// aparece sozinha vira ruído num diff que não a pediu.
export default tseslint.config(
  { ignores: ["dist", "coverage", "node_modules", "src/api/schema.d.ts"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],

      // O `catch (erro: unknown)` do cliente e o `data` do JSONB são unknown de
      // propósito; o que não pode passar é `any` implícito virando acesso livre.
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unsafe-member-access": "error",

      // Promise ignorada em handler de evento é a origem silenciosa de erro não
      // tratado — e este app é quase todo I/O.
      "@typescript-eslint/no-floating-promises": "error",
    },
  },
  {
    // Arquivos de teste e utilitários de teste não entram no bundle, então
    // fast refresh não se aplica a eles. `renderizar` convive com componentes
    // de apoio no mesmo arquivo de propósito — é o helper, não uma tela.
    files: ["**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
);
