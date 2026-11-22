import { Route, Routes } from "react-router-dom";
import { Marco } from "./componentes/Marco";
import { NoEncontrado } from "./componentes/NoEncontrado";
import { Protegida } from "./componentes/Protegida";
import { Entrar, Registro } from "./paginas/Cuenta";
import { DatoPagina, Datos, SeriePagina } from "./paginas/Datos";
import { FiguraPagina, Figuras } from "./paginas/Figuras";
import { Inicio, PerfilPagina, PublicacionDetalle, TendenciaPagina, Tendencias } from "./paginas/Red";
import { Buscar } from "./paginas/Buscar";
import { ComunidadPagina, Comunidades } from "./paginas/Comunidades";
import { Revisiones } from "./paginas/Revisiones";
import { Equipo } from "./paginas/Equipo";
import { AnalisisPagina, Analizar } from "./paginas/Analizar";
import { TemaPagina, Temas } from "./paginas/TemasDelDia";

export function App() {
  return (
    <Routes>
      <Route path="/entrar" element={<Entrar />} />
      <Route path="/registro" element={<Registro />} />
      <Route path="*" element={
        <Marco>
          <Routes>
            <Route path="/" element={<Inicio />} />
            <Route path="/publicacion/:id" element={<PublicacionDetalle />} />
            <Route path="/perfil/:nombre" element={<PerfilPagina />} />
            <Route path="/temas" element={<Temas />} />
            <Route path="/temas/:id" element={<TemaPagina />} />
            <Route path="/tendencias" element={<Tendencias />} />
            <Route path="/tendencias/:etiqueta" element={<TendenciaPagina />} />
            <Route path="/analizar" element={<Analizar />} />
            <Route path="/analizar/:id" element={<AnalisisPagina />} />
            <Route path="/figuras" element={<Figuras />} />
            <Route path="/figuras/:id" element={<FiguraPagina />} />
            <Route path="/datos" element={<Datos />} />
            <Route path="/datos/:codigo" element={<SeriePagina />} />
            <Route path="/datos/dato/:id" element={<DatoPagina />} />
            <Route path="/revisiones" element={<Protegida roles={["verificador", "admin"]}><Revisiones /></Protegida>} />
            <Route path="/equipo" element={<Equipo />} />
            <Route path="/buscar" element={<Buscar />} />
            <Route path="/comunidades" element={<Comunidades />} />
            <Route path="/comunidades/:id" element={<ComunidadPagina />} />
            <Route path="*" element={<NoEncontrado />} />
          </Routes>
        </Marco>
      } />
    </Routes>
  );
}
