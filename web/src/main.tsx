// Tipografía (decisión 32, sistema "Claridad"): títulos y cifras destacadas en Bricolage Grotesque,
// texto en Atkinson Hyperlegible Next, tablas en Atkinson Hyperlegible Mono. Todas OFL y alojadas aquí.
import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "@fontsource-variable/atkinson-hyperlegible-next/wght.css";
import "@fontsource-variable/atkinson-hyperlegible-next/wght-italic.css";
import "@fontsource-variable/atkinson-hyperlegible-mono/wght.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./estilos/titular.css";
import "./estilos/base.css";
import "./estilos/app.css";
import "./estilos/profundidad.css";
import { ProveedorSesion } from "./sesion";

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <BrowserRouter>
      <ProveedorSesion>
        <App />
      </ProveedorSesion>
    </BrowserRouter>
  </StrictMode>,
);
