import { useState, type ReactNode } from "react";
import { FondoSeda } from "../componentes/FondoSeda";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, destinoSeguro, ErrorApi } from "../api";
import { BotonTema } from "../componentes/BotonTema";
import { PanelVivo } from "../componentes/PanelVivo";
import { useSesion } from "../sesion";

const Ojo = ({ abierto }: { abierto: boolean }) => (
  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />
    {!abierto && <path d="M4 20 20 4" />}
  </svg>
);

function Campo({ etiqueta, icono, children }: { etiqueta: string; icono: ReactNode; children: ReactNode }) {
  return (
    <label className="campo-icono">
      <span className="campo-icono__etiqueta">{etiqueta}</span>
      <span className="campo-icono__caja">{icono}{children}</span>
    </label>
  );
}

const Sobre = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>;
const Candado = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>;
const Persona = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" /></svg>;
const Arroba = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M16 12v1.5a2.5 2.5 0 0 0 5 0V12a9 9 0 1 0-3.5 7.1" /></svg>;

function CampoClave({ valor, cambiar, nueva }: { valor: string; cambiar: (v: string) => void; nueva?: boolean }) {
  const [visible, setVisible] = useState(false);
  return (
    <Campo etiqueta="Contraseña" icono={<Candado />}>
      <input type={visible ? "text" : "password"} value={valor} onChange={(e) => cambiar(e.target.value)} required
        minLength={nueva ? 8 : undefined} autoComplete={nueva ? "new-password" : "current-password"}
        placeholder={nueva ? "Al menos 8 caracteres" : "Tu contraseña"} />
      <button type="button" className="campo-icono__ver" onClick={() => setVisible(!visible)}
        aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={visible}><Ojo abierto={visible} /></button>
    </Campo>
  );
}

function Pantalla({ referencia, titulo, ayuda, children }: { referencia: string; titulo: ReactNode; ayuda: string; children: ReactNode }) {
  return (
    <>
    <FondoSeda />
    <div className="acceso">
      <PanelVivo />
      <section className="acceso__panel">
        <div className="acceso__arriba"><Link to="/" className="enlace-suave">← Volver a Parrhesia</Link><BotonTema /></div>
        <div className="acceso__formulario">
          <p className="sello">{referencia}</p>
          <h1 className="acceso__titulo">{titulo}</h1>
          <p className="acceso__ayuda">{ayuda}</p>
          {children}
        </div>
      </section>
    </div>
    </>
  );
}

export function Entrar() {
  const { entrar, usuario, cargando } = useSesion();
  const navegar = useNavigate();
  const [parametros] = useSearchParams();
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await entrar(correo, clave);
      navegar(destinoSeguro(parametros.get("siguiente")), { replace: true });
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo iniciar sesión. Revisa tu conexión e inténtalo de nuevo.");
      setClave("");
    } finally {
      setEnviando(false);
    }
  };

  if (!cargando && usuario) return <Navigate to={destinoSeguro(parametros.get("siguiente"))} replace />;
  return (
    <Pantalla referencia="Acceso" titulo={<>Inicia <em>sesión</em></>} ayuda="Continúa con el correo y la contraseña de tu cuenta.">
      <form onSubmit={enviar} className="acceso__campos" noValidate={false}>
        <Campo etiqueta="Correo" icono={<Sobre />}>
          <input type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} autoComplete="email" placeholder="tu@correo.co" required autoFocus />
        </Campo>
        <CampoClave valor={clave} cambiar={setClave} />
        {error && <p className="aviso" role="alert">{error}</p>}
        <button className="boton boton--ancho" disabled={enviando}>{enviando ? "Entrando…" : "Entrar a Parrhesia"} <span aria-hidden="true">→</span></button>
      </form>
      <p className="acceso__nota">¿No tienes cuenta? <Link to="/registro" className="marca-texto">Créala aquí</Link></p>
      <p className="acceso__seguridad">Sesión protegida: ningún script de la página puede leerla y se cierra en el servidor al salir. Tras 5 intentos fallidos, el acceso se pausa 15 minutos.</p>
    </Pantalla>
  );
}

export function fuerza(clave: string): { nivel: number; texto: string } {
  let puntos = 0;
  if (clave.length >= 8) puntos++;
  if (clave.length >= 12) puntos++;
  if (/[a-záéíóúñ]/.test(clave) && /[A-ZÁÉÍÓÚÑ]/.test(clave)) puntos++;
  if (/\d/.test(clave)) puntos++;
  if (/[^\p{L}\d]/u.test(clave)) puntos++;
  const nivel = Math.min(4, puntos);
  return { nivel, texto: ["Muy corta", "Débil", "Aceptable", "Buena", "Fuerte"][nivel] };
}

export function Registro() {
  const { entrar, usuario, cargando } = useSesion();
  const navegar = useNavigate();
  const [datos, setDatos] = useState({ nombre_visible: "", nombre_usuario: "", correo: "", clave: "" });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const cambiar = (campo: keyof typeof datos) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDatos({ ...datos, [campo]: campo === "nombre_usuario" ? e.target.value.toLowerCase() : e.target.value });
  const f = fuerza(datos.clave);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await api("/social/v1/cuentas", { metodo: "POST", cuerpo: datos });
      await entrar(datos.correo, datos.clave);
      navegar("/", { replace: true });
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo crear la cuenta. Inténtalo de nuevo.");
    } finally {
      setEnviando(false);
    }
  };

  if (!cargando && usuario && !enviando) return <Navigate to="/" replace />;
  return (
    <Pantalla referencia="Nueva cuenta" titulo={<>Crea tu <em>cuenta</em></>} ayuda="Opina con libertad y consulta el dato oficial detrás de cada cifra.">
      <form onSubmit={enviar} className="acceso__campos">
        <Campo etiqueta="Nombre visible" icono={<Persona />}>
          <input value={datos.nombre_visible} onChange={cambiar("nombre_visible")} maxLength={60} placeholder="Como quieres que te vean" required autoFocus />
        </Campo>
        <Campo etiqueta="Nombre de usuario" icono={<Arroba />}>
          <input value={datos.nombre_usuario} onChange={cambiar("nombre_usuario")} pattern="[a-z0-9_]{3,30}" maxLength={30}
            title="De 3 a 30 letras minúsculas, números o guion bajo" placeholder="sin_espacios" autoComplete="username" required />
        </Campo>
        <Campo etiqueta="Correo" icono={<Sobre />}>
          <input type="email" value={datos.correo} onChange={cambiar("correo")} autoComplete="email" placeholder="tu@correo.co" required />
        </Campo>
        <CampoClave valor={datos.clave} cambiar={(v) => setDatos({ ...datos, clave: v })} nueva />
        {datos.clave && (
          <div className="fuerza" aria-live="polite">
            <span className="fuerza__barras">{[1, 2, 3, 4].map((n) => <i key={n} className={n <= f.nivel ? "activa" : ""} />)}</span>
            <small>{f.texto}</small>
          </div>
        )}
        {error && <p className="aviso" role="alert">{error}</p>}
        <button className="boton boton--ancho" disabled={enviando}>{enviando ? "Creando…" : "Crear mi cuenta"} <span aria-hidden="true">→</span></button>
      </form>
      <p className="acceso__nota">¿Ya tienes cuenta? <Link to="/entrar" className="marca-texto">Inicia sesión</Link></p>
      <p className="acceso__seguridad">La contraseña se guarda cifrada con argon2id: nadie puede leerla, ni siquiera el equipo. Parrhesia no asigna a nadie un lado político.</p>
    </Pantalla>
  );
}
