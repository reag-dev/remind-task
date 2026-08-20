import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // 3000 não é escolha estética: é o que o backend já tem em
    // CORS_ALLOWED_ORIGINS (.env.example). Trocar aqui exige trocar lá.
    port: 3000,
    // Falha se a porta estiver ocupada, em vez de subir na 3001 — onde o CORS
    // recusaria toda requisição e o sintoma apareceria como erro de rede.
    strictPort: true,
  },
});
