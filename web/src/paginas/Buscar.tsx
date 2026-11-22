// Buscar personas por nombre (y, si se escribe #, ir a la etiqueta). Solo cuentas activas y solo
// datos públicos. Los resultados no se ordenan por afinidad política: por nombre y parecido de texto.
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Avatar } from "../componentes/Avatar";
import * as I from "../componentes/Iconos";
import { useSesion } from "../sesion";

interface Persona { nombre_usuario: string; nombre_visible: string; foto: string | null; biografia: string | null; seguidores: number; lo_sigo: boolean }

export function Buscar() {
  const [parametros, setParametros] = useSearchParams();
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const q = parametros.get("q") ?? "";
  const [texto, setTexto] = useState(q);
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [cambiando, setCambiando] = useState<string | null>(null);

  // La dirección refleja la búsqueda (se puede compartir); se consulta tras una pausa al escribir.
  useEffect(() => {
    const t = setTimeout(() => setParametros(texto.trim() ? { q: texto.trim() } : {}, { replace: true }), 300);
    return () => clearTimeout(t);
  }, [texto]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const limpio = q.replace(/^@/, "").trim();
    if (limpio.startsWith("#") || limpio.length < 2) return setPersonas(null);
    let vigente = true;
    api<{ usuarios: Persona[] }>(`/social/v1/usuarios?q=${encodeURIComponent(limpio)}`)
      .then((r) => vigente && setPersonas(r.usuarios)).catch(() => vigente && setPersonas([]));
    return () => { vigente = false; };
  }, [q, usuario?.id]);

  const seguir = async (p: Persona) => {
    if (!usuario) return navegar(`/entrar?siguiente=${encodeURIComponent(`/buscar?q=${q}`)}`);
    setCambiando(p.nombre_usuario);
    try {
      await api(`/social/v1/usuarios/${p.nombre_usuario}/seguidores/yo`, { metodo: p.lo_sigo ? "DELETE" : "PUT" });
      setPersonas((l) => l?.map((x) => x.nombre_usuario === p.nombre_usuario
        ? { ...x, lo_sigo: !x.lo_sigo, seguidores: x.seguidores + (x.lo_sigo ? -1 : 1) } : x) ?? null);
    } finally {
      setCambiando(null);
    }
  };

  const etiqueta = q.startsWith("#") ? q.slice(1).toLowerCase().replace(/[^a-záéíóúñü0-9_]/g, "") : "";
  return (
    <>
      <h1 className="titulo-seccion">Buscar</h1>
      <form className="buscar-campo" role="search" onSubmit={(e) => e.preventDefault()}>
        <I.Buscar />
        <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Nombre de una persona, @usuario o #etiqueta"
          aria-label="Buscar personas o etiquetas" autoFocus />
      </form>
      {etiqueta && (
        <Link to={`/tendencias/${etiqueta}`} className="tarjeta buscar-etiqueta">
          Ver lo publicado con <strong>#{etiqueta}</strong> <I.Flecha width={16} />
        </Link>
      )}
      {!etiqueta && q.length > 0 && q.replace(/^@/, "").length < 2 && <p className="tenue">Escribe al menos dos letras.</p>}
      {personas?.length === 0 && <p className="tenue">No hay personas con ese nombre.</p>}
      {personas && personas.length > 0 && (
        <ul className="personas" aria-label="Personas">
          {personas.map((p) => (
            <li key={p.nombre_usuario} className="persona tarjeta">
              <Link to={`/perfil/${p.nombre_usuario}`} className="persona__quien">
                <Avatar nombre={p.nombre_visible} foto={p.foto} />
                <span>
                  <strong>{p.nombre_visible}</strong>
                  <small className="tenue">@{p.nombre_usuario} · <span className="cifra">{p.seguidores}</span> {p.seguidores === 1 ? "seguidor" : "seguidores"}</small>
                  {p.biografia && <span className="persona__bio">{p.biografia}</span>}
                </span>
              </Link>
              {usuario?.nombre_usuario !== p.nombre_usuario && (
                <button className={`boton boton--pequeno ${p.lo_sigo ? "boton--borde" : ""}`} onClick={() => seguir(p)}
                  disabled={cambiando === p.nombre_usuario} aria-pressed={p.lo_sigo}>
                  {p.lo_sigo ? "Siguiendo" : "Seguir"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
