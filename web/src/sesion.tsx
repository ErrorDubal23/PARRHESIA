import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import type { Usuario } from "./tipos";

interface Sesion {
  usuario: Usuario | null;
  cargando: boolean;
  entrar: (correo: string, clave: string) => Promise<void>;
  salir: () => Promise<void>;
  refrescar: () => Promise<void>;
}

const Contexto = createContext<Sesion | null>(null);
// Avisa a las otras pestañas abiertas cuando se entra o se sale.
const canal = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("parrhesia-sesion") : null;

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(true);

  const consultar = useCallback(() => {
    api<Usuario>("/social/v1/yo").then(setUsuario).catch(() => setUsuario(null)).finally(() => setCargando(false));
  }, []);

  useEffect(() => {
    consultar();
    const vencida = () => setUsuario(null);
    const mensaje = (e: MessageEvent) => (e.data === "salio" ? setUsuario(null) : consultar());
    window.addEventListener("sesion-vencida", vencida);
    canal?.addEventListener("message", mensaje);
    return () => {
      window.removeEventListener("sesion-vencida", vencida);
      canal?.removeEventListener("message", mensaje);
    };
  }, [consultar]);

  const entrar = useCallback(async (correo: string, clave: string) => {
    const r = await api<{ usuario: Usuario }>("/social/v1/sesiones", { metodo: "POST", cuerpo: { correo, clave } });
    setUsuario(r.usuario);
    canal?.postMessage("entro");
  }, []);

  const salir = useCallback(async () => {
    try {
      await api("/social/v1/sesiones/actual", { metodo: "DELETE" }); // revoca la sesión en el servidor
    } finally {
      setUsuario(null);
      canal?.postMessage("salio");
    }
  }, []);

  // Después de editar el perfil: vuelve a leer la propia cuenta y avisa a las otras pestañas.
  const refrescar = useCallback(async () => {
    setUsuario(await api<Usuario>("/social/v1/yo"));
    canal?.postMessage("entro");
  }, []);

  return <Contexto.Provider value={{ usuario, cargando, entrar, salir, refrescar }}>{children}</Contexto.Provider>;
}

/** Lleva a entrar y, después, de vuelta a la página actual. */
export function useIrAEntrar() {
  const navegar = useNavigate();
  const { pathname, search } = useLocation();
  return () => navegar(`/entrar?siguiente=${encodeURIComponent(pathname + search)}`);
}

export function useSesion() {
  const s = useContext(Contexto);
  if (!s) throw new Error("useSesion fuera de ProveedorSesion");
  return s;
}
