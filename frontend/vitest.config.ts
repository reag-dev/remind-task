import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Fixo aqui em vez de vir do .env: teste que depende do ambiente da máquina
    // passa no laptop e falha no CI. O MSW intercepta esta origem.
    env: { VITE_API_URL: "http://localhost:8000/api" },
    coverage: {
      provider: "v8",
      // Espelha o fail_under = 85 do .coveragerc do backend.
      thresholds: { lines: 85, functions: 85, branches: 85, statements: 85 },

      // `include` não é detalhe. Sem ele o v8 só relata arquivos que algum
      // teste importou — um módulo inteiro sem teste nenhum simplesmente não
      // aparece, e a porcentagem sobe. O número passaria a medir "o que eu
      // testei do que resolvi testar", que não é cobertura. (No Vitest 3 isso
      // se ligava com `all: true`; a opção saiu no 4 e o `include` assumiu o
      // papel.)
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        // Gerado por `npm run api:types`; não é código nosso.
        "src/api/schema.d.ts",
        // Só declarações de tipo — não há execução para cobrir.
        "src/env.d.ts",
        "src/api/tipos.ts",
        // Ponto de entrada e composição de providers/rotas: sem ramo de
        // decisão. Mesmo critério do .coveragerc do backend, que omite
        // manage.py e config/wsgi.py.
        "src/main.tsx",
        "src/App.tsx",
        "src/test/**",
        "**/*.config.*",
      ],
    },
  },
});
