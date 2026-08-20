import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { criarQueryClient } from "./api/query.ts";
import { AuthProvider } from "./auth/AuthProvider.tsx";
import { Layout } from "./components/Layout.tsx";
import { Login } from "./routes/Login.tsx";
import { Registro } from "./routes/Registro.tsx";
import { RotaProtegida } from "./routes/RotaProtegida.tsx";
import { TabelaColunas } from "./routes/TabelaColunas.tsx";
import { TabelaDetalhe } from "./routes/TabelaDetalhe.tsx";
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
            <Route element={<RotaProtegida />}>
              <Route element={<Layout />}>
                <Route path="/" element={<Tabelas />} />
                <Route path="/tabelas/nova" element={<TabelaNova />} />
                <Route path="/tabelas/:id" element={<TabelaDetalhe />} />
                <Route path="/tabelas/:id/colunas" element={<TabelaColunas />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
