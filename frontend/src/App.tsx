import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { criarQueryClient } from "./api/query.ts";
import { AuthProvider } from "./auth/AuthProvider.tsx";
import { Layout } from "./components/Layout.tsx";
import { EsqueciSenha } from "./routes/EsqueciSenha.tsx";
import { Login } from "./routes/Login.tsx";
import { RedefinirSenha } from "./routes/RedefinirSenha.tsx";
import { Registro } from "./routes/Registro.tsx";
import { RotaProtegida } from "./routes/RotaProtegida.tsx";
import { Alertas } from "./routes/Alertas.tsx";
import { Conta } from "./routes/Conta.tsx";
import { TabelaColunas } from "./routes/TabelaColunas.tsx";
import { TabelaRegras } from "./routes/TabelaRegras.tsx";
import { TabelaRegistros } from "./routes/TabelaRegistros.tsx";
import { TabelaNova } from "./routes/TabelaNova.tsx";
import { Tabelas } from "./routes/Tabelas.tsx";

export function App() {
  // `useState` com inicializador de função, não `criarQueryClient()` direto no
  // corpo: a segunda forma criaria um cliente novo a cada render, jogando fora
  // o cache inteiro. Em <StrictMode> o efeito seria visível já na montagem.
  const [cliente] = useState(criarQueryClient);

  return (
    <QueryClientProvider client={cliente}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/registro" element={<Registro />} />
            <Route path="/esqueci-senha" element={<EsqueciSenha />} />
            <Route path="/redefinir-senha" element={<RedefinirSenha />} />
            <Route element={<RotaProtegida />}>
              <Route element={<Layout />}>
                <Route path="/" element={<Tabelas />} />
                <Route path="/tabelas/nova" element={<TabelaNova />} />
                <Route path="/tabelas/:id" element={<TabelaRegistros />} />
                <Route path="/tabelas/:id/colunas" element={<TabelaColunas />} />
                <Route path="/tabelas/:id/alertas" element={<TabelaRegras />} />
                <Route path="/alertas" element={<Alertas />} />
                <Route path="/conta" element={<Conta />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
