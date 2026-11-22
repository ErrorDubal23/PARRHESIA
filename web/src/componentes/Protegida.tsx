// Rutas que piden sesión (y, si corresponde, un rol). Sin sesión lleva a entrar y luego devuelve a
// donde ibas; con un rol que no alcanza, lo dice. El servidor revisa lo mismo en cada petición: esto
// solo evita mostrar pantallas que de todos modos no van a cargar.
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSesion } from "../sesion";
import type { Usuario } from "../tipos";
import { NoEncontrado } from "./NoEncontrado";

export function Protegida({ roles, children }: { roles?: Usuario["rol"][]; children: ReactNode }) {
  const { usuario, cargando } = useSesion();
  const { pathname, search } = useLocation();
  if (cargando) return <span className="cargando"><i /><i /><i /></span>;
  if (!usuario) return <Navigate to={`/entrar?siguiente=${encodeURIComponent(pathname + search)}`} replace />;
  if (roles && !roles.includes(usuario.rol)) {
    return <NoEncontrado codigo="403" titulo="Esta sección es para el equipo de verificación."
      texto="Tu cuenta no tiene ese permiso. Si crees que debería tenerlo, habla con un administrador." />;
  }
  return <>{children}</>;
}
