import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useIrAEntrar, useSesion } from "../sesion";
import type { Publicacion } from "../tipos";
import { BotonTema } from "./BotonTema";
import { Compositor } from "./Compositor";
import { CarruselTemas } from "./Temas";
import * as I from "./Iconos";
import { Avatar } from "./Avatar";
import { FondoSeda } from "./FondoSeda";
import { AnalisisProvider } from "./AnalisisEnCurso";
import { useRelieve } from "./Relieve";

export interface ComunidadDestino { id: string; nombre: string; privacidad: "publica" | "privada" }
const Publicar = createContext<(respondeA?: Publicacion | null, comunidad?: ComunidadDestino) => void>(() => {});
export const usePublicar = () => useContext(Publicar);

const SECCIONES = [
  { a: "/", texto: "Inicio", icono: I.Inicio },
  { a: "/temas", texto: "Temas del día", icono: I.Temas },
  { a: "/tendencias", texto: "Tendencias", icono: I.Tendencias },
  { a: "/comunidades", texto: "Comunidades", icono: I.Comunidades },
  { a: "/figuras", texto: "Figuras públicas", icono: I.Figuras },
  { a: "/datos", texto: "Datos oficiales", icono: I.Datos },
  { a: "/analizar", texto: "Analizar enlace", icono: I.Enlace },
];

export function Marco({ children }: { children: ReactNode }) {
  const { usuario, salir } = useSesion();
  const navegar = useNavigate();
  const irAEntrar = useIrAEntrar();
  const [compositor, setCompositor] = useState<{ abierto: boolean; respondeA?: Publicacion | null; comunidad?: ComunidadDestino }>({ abierto: false });
  const [busqueda, setBusqueda] = useState("");
  // Cada página nueva entra con su animación (profundidad.css); dentro de la misma página no se repite.
  const ruta = useLocation().pathname;
  useRelieve();
  // Cada página nueva empieza arriba (en escritorio se desplaza el cuerpo; en celular, la ventana).
  useEffect(() => { document.body.scrollTo?.(0, 0); window.scrollTo(0, 0); }, [ruta]);

  const abrir = (respondeA?: Publicacion | null, comunidad?: ComunidadDestino) => {
    if (!usuario) return irAEntrar();
    setCompositor({ abierto: true, respondeA: respondeA ?? null, comunidad });
  };

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      const escribiendo = (e.target as HTMLElement)?.closest("input, textarea, select, [contenteditable]");
      if (e.key.toLowerCase() === "n" && !escribiendo && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        abrir();
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  });

  const buscar = (e: React.FormEvent) => {
    e.preventDefault();
    const texto = busqueda.trim();
    if (!texto) return;
    // Con # va a la etiqueta; lo demás busca personas.
    if (texto.startsWith("#")) navegar(`/tendencias/${encodeURIComponent(texto.slice(1).toLowerCase())}`);
    else navegar(`/buscar?q=${encodeURIComponent(texto)}`);
    setBusqueda("");
  };

  return (
    <Publicar.Provider value={abrir}>
      <AnalisisProvider>
      <FondoSeda />
      <div className="marco">
        <aside className="lateral">
          <Link to="/" className="lateral__marca" aria-label="Parrhesia, inicio">
            <I.Logo tamano={44} aleteo="al-pasar" />
            <span>PARRHESIA</span>
          </Link>
          <nav className="lateral__nav" aria-label="Secciones">
            {SECCIONES.map(({ a, texto, icono: Icono }) => (
              <NavLink key={a} to={a} end={a === "/"} className="lateral__enlace">
                <Icono /><span>{texto}</span>
              </NavLink>
            ))}
            {usuario && usuario.rol !== "usuario" && (
              <>
                <NavLink to="/revisiones" className="lateral__enlace">
                  <I.Revisiones /><span>Revisiones</span>
                </NavLink>
                <NavLink to="/equipo" className="lateral__enlace">
                  <I.Comunidades /><span>Equipo</span>
                </NavLink>
              </>
            )}
          </nav>
          <div className="lateral__pie">
            <div className="lateral__tema"><span>Apariencia</span><BotonTema /></div>
            {usuario ? (
              <>
                {/* La cuenta lleva al perfil: reemplaza a "Mi perfil" del menú. */}
                <NavLink to={`/perfil/${usuario.nombre_usuario}`} className="lateral__yo" title="Ver mi perfil">
                  <Avatar nombre={usuario.nombre_visible} foto={usuario.foto} />
                  <span><strong>{usuario.nombre_visible}</strong><small>@{usuario.nombre_usuario}</small></span>
                  <I.Flecha width={14} />
                </NavLink>
                <button className="boton-texto" onClick={async () => { await salir(); navegar("/entrar"); }}><I.Salir /> Cerrar sesión</button>
              </>
            ) : (
              <Link to="/entrar" className="boton boton--borde">Entrar</Link>
            )}
          </div>
        </aside>

        <div className="centro">
          <header className="superior">
            <form className="buscador" onSubmit={buscar} role="search">
              <I.Buscar />
              <input value={busqueda} onChange={(e) => setBusqueda(e.target.value)} placeholder="Buscar personas o #etiquetas"
                aria-label="Buscar personas o etiquetas" />
            </form>
            <BotonTema className="solo-movil" />
          </header>
          <div className="contenido">
            <main className="principal" key={ruta}>{children}</main>
            <ColumnaDerecha />
          </div>
        </div>
      </div>
      <button className="publicar-flotante" onClick={() => abrir()} title="Publicar (tecla N)" aria-label="Publicar">
        <I.Lapiz width={22} /><span>Publicar</span>
      </button>
      <Compositor abierto={compositor.abierto} respondeA={compositor.respondeA} comunidad={compositor.comunidad}
        cerrar={() => setCompositor({ abierto: false })} />
      </AnalisisProvider>
    </Publicar.Provider>
  );
}

function ColumnaDerecha() {
  const { usuario } = useSesion();
  const enTemas = useLocation().pathname.startsWith("/temas"); // en su propia página no se repiten
  const [voces, setVoces] = useState<{ nombre_usuario: string; nombre_visible: string; foto: string | null; temas: string[] }[]>([]);
  const [sugerencias, setSugerencias] = useState<{ usuario_id: string; nombre_usuario: string; nombre_visible: string; foto: string | null; en_comun: number }[]>([]);

  // Primero personas que discuten tus temas fuera de tu red; si no hay, las de tu red ampliada.
  useEffect(() => {
    if (!usuario) return;
    api<{ personas: typeof voces }>("/social/v1/personas/otras-voces").then((r) => {
      setVoces(r.personas);
      if (r.personas.length === 0) api<{ sugerencias: typeof sugerencias }>("/social/v1/sugerencias").then((s) => setSugerencias(s.sugerencias)).catch(() => {});
    }).catch(() => {});
  }, [usuario]);

  return (
    <aside className="derecha">
      {!enTemas && <CarruselTemas />}
      {usuario && voces.length > 0 && (
        <section className="tarjeta bloque">
          <h2 className="subtitulo">Otras voces sobre tus temas</h2>
          <p className="tenue sugeridas__nota">Personas fuera de tu red que hablan de lo mismo que tú.</p>
          <ul className="personas">
            {voces.slice(0, 4).map((v) => (
              <Persona key={v.nombre_usuario} nombre_usuario={v.nombre_usuario} nombre_visible={v.nombre_visible} foto={v.foto}
                detalle={v.temas.map((t) => `#${t}`).join(" ")} />
            ))}
          </ul>
        </section>
      )}
      {usuario && voces.length === 0 && sugerencias.length > 0 && (
        <section className="tarjeta bloque">
          <h2 className="subtitulo">A quién seguir</h2>
          <ul className="personas">
            {sugerencias.slice(0, 4).map((s) => (
              <Persona key={s.usuario_id} nombre_usuario={s.nombre_usuario} nombre_visible={s.nombre_visible} foto={s.foto}
                detalle={`${s.en_comun} en común`} />
            ))}
          </ul>
        </section>
      )}
      <p className="derecha__nota tenue">
        Parrhesia no dice quién tiene razón. Muestra si una conclusión se sostiene, se debilita o se
        invierte frente al dato oficial.
      </p>
    </aside>
  );
}

/** Una persona sugerida: avatar, nombre, @usuario y el botón para seguirla ahí mismo. */
function Persona({ nombre_usuario, nombre_visible, foto, detalle }: { nombre_usuario: string; nombre_visible: string; foto: string | null; detalle: string }) {
  const [sigo, setSigo] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const alternar = async () => {
    setOcupado(true);
    try {
      await api(`/social/v1/usuarios/${nombre_usuario}/seguidores/yo`, { metodo: sigo ? "DELETE" : "PUT" });
      setSigo(!sigo);
    } finally {
      setOcupado(false);
    }
  };
  return (
    <li className="persona">
      <Link to={`/perfil/${nombre_usuario}`} className="persona__enlace">
        <Avatar nombre={nombre_visible} foto={foto} />
        <span><strong>{nombre_visible}</strong><small>@{nombre_usuario}</small><small className="persona__detalle">{detalle}</small></span>
      </Link>
      <button className={`boton-seguir${sigo ? " boton-seguir--activo" : ""}`} onClick={alternar} disabled={ocupado} aria-pressed={sigo}>
        {sigo ? "Siguiendo" : "Seguir"}
      </button>
    </li>
  );
}
