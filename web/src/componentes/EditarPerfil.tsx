// Panel lateral para editar la propia cuenta, sin recorrer varias pantallas: perfil público (foto,
// nombres, biografía), correo, contraseña y desactivación. Cada sección se guarda por separado y
// dice qué pasó. Los cambios sensibles piden la contraseña actual (lo exige el servidor).
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, ErrorApi } from "../api";
import { fuerza } from "../paginas/Cuenta";
import { useSesion } from "../sesion";
import type { Usuario } from "../tipos";
import { Avatar } from "./Avatar";

const MAX_BIO = 280;
const MAX_FOTO = 2 * 1024 * 1024;
type Aviso = { tipo: "ok" | "error"; texto: string } | null;
const mensaje = (e: unknown, defecto: string) => (e instanceof ErrorApi ? e.message : defecto);

function Mensaje({ aviso }: { aviso: Aviso }) {
  if (!aviso) return null;
  return <p className={aviso.tipo === "ok" ? "panel-cuenta__ok" : "aviso"} role={aviso.tipo === "ok" ? "status" : "alert"}>{aviso.texto}</p>;
}

function Seccion({ titulo, ayuda, children }: { titulo: string; ayuda?: string; children: ReactNode }) {
  return (
    <section className="panel-cuenta__seccion">
      <h3>{titulo}</h3>
      {ayuda && <p className="tenue">{ayuda}</p>}
      {children}
    </section>
  );
}

/** Disponibilidad del nombre de usuario mientras se escribe (con una pausa para no consultar cada tecla). */
function useDisponibilidad(nombre: string, actual: string) {
  const [estado, setEstado] = useState<"actual" | "revisando" | "disponible" | "en_uso" | "invalido">("actual");
  useEffect(() => {
    const limpio = nombre.trim().toLowerCase();
    if (limpio === actual) return setEstado("actual");
    if (!/^[a-z0-9_]{3,30}$/.test(limpio)) return setEstado("invalido");
    setEstado("revisando");
    const t = setTimeout(() => {
      api<{ estado: "disponible" | "en_uso" | "invalido" }>(`/social/v1/cuentas/disponible?nombre_usuario=${encodeURIComponent(limpio)}`)
        .then((r) => setEstado(r.estado)).catch(() => setEstado("actual"));
    }, 350);
    return () => clearTimeout(t);
  }, [nombre, actual]);
  return estado;
}

const TEXTO_NOMBRE = {
  actual: "Es tu nombre de usuario actual.",
  revisando: "Revisando…",
  disponible: "Disponible.",
  en_uso: "Ya lo usa otra cuenta.",
  invalido: "De 3 a 30 letras minúsculas, números o guion bajo.",
};

export function EditarPerfil({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const { usuario, refrescar } = useSesion();
  const navegar = useNavigate();
  const dialogo = useRef<HTMLDialogElement>(null);
  const [yo, setYo] = useState<Usuario | null>(null);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (abierto && !d.open) {
      d.showModal();
      api<Usuario>("/social/v1/yo").then(setYo).catch(() => {});
    }
    if (!abierto && d.open) d.close();
  }, [abierto]);

  return (
    <dialog ref={dialogo} className="panel-cuenta" onClose={cerrar} aria-labelledby="titulo-panel-cuenta">
      <div className="panel-cuenta__cabecera">
        <h2 id="titulo-panel-cuenta">Editar perfil</h2>
        <button type="button" className="boton-icono" onClick={cerrar} aria-label="Cerrar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>
      {!yo || !usuario ? <span className="cargando"><i /><i /><i /></span> : (
        <div className="panel-cuenta__cuerpo">
          <PerfilPublico yo={yo} alGuardar={async (nuevoNombre) => {
            await refrescar();
            const actualizado = await api<Usuario>("/social/v1/yo");
            setYo(actualizado);
            if (nuevoNombre) navegar(`/perfil/${nuevoNombre}`, { replace: true });
          }} />
          <Correo actual={yo.correo ?? ""} alGuardar={(correo) => setYo({ ...yo, correo })} />
          <Clave />
          <Desactivar alTerminar={() => { cerrar(); navegar("/entrar", { replace: true }); window.location.reload(); }} />
        </div>
      )}
    </dialog>
  );
}

function PerfilPublico({ yo, alGuardar }: { yo: Usuario; alGuardar: (nuevoNombre?: string) => Promise<void> }) {
  const [visible, setVisible] = useState(yo.nombre_visible);
  const [nombre, setNombre] = useState(yo.nombre_usuario);
  const [bio, setBio] = useState(yo.biografia ?? "");
  const [foto, setFoto] = useState(yo.foto);
  const [aviso, setAviso] = useState<Aviso>(null);
  const [avisoFoto, setAvisoFoto] = useState<Aviso>(null);
  const [enviando, setEnviando] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const disponibilidad = useDisponibilidad(nombre, yo.nombre_usuario);

  const cambios = visible.trim() !== yo.nombre_visible || nombre.trim().toLowerCase() !== yo.nombre_usuario || bio.trim() !== (yo.biografia ?? "");
  const nombreValido = disponibilidad === "actual" || disponibilidad === "disponible";

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setAviso(null);
    const nuevoNombre = nombre.trim().toLowerCase() !== yo.nombre_usuario ? nombre.trim().toLowerCase() : undefined;
    try {
      await api("/social/v1/yo", { metodo: "PATCH", cuerpo: {
        nombre_visible: visible.trim() !== yo.nombre_visible ? visible.trim() : null,
        nombre_usuario: nuevoNombre ?? null,
        biografia: bio.trim() !== (yo.biografia ?? "") ? bio.trim() : null,
      } });
      setAviso({ tipo: "ok", texto: "Cambios guardados." });
      await alGuardar(nuevoNombre);
    } catch (err) {
      setAviso({ tipo: "error", texto: mensaje(err, "No se pudieron guardar los cambios. Inténtalo de nuevo.") });
    } finally {
      setEnviando(false);
    }
  };

  const subir = async (archivo: File | undefined) => {
    if (!archivo) return;
    setAvisoFoto(null);
    if (!["image/jpeg", "image/png", "image/webp"].includes(archivo.type)) return setAvisoFoto({ tipo: "error", texto: "La foto debe ser JPG, PNG o WebP." });
    if (archivo.size > MAX_FOTO) return setAvisoFoto({ tipo: "error", texto: "La foto pesa más de 2 MB." });
    const datos = new FormData();
    datos.append("foto", archivo);
    setSubiendo(true);
    try {
      const r = await api<{ foto: string }>("/social/v1/yo/foto", { metodo: "PUT", cuerpo: datos });
      setFoto(r.foto);
      setAvisoFoto({ tipo: "ok", texto: "Foto actualizada." });
      await alGuardar();
    } catch (err) {
      setAvisoFoto({ tipo: "error", texto: mensaje(err, "No se pudo subir la foto.") });
    } finally {
      setSubiendo(false);
    }
  };

  const quitar = async () => {
    setAvisoFoto(null);
    try {
      await api("/social/v1/yo/foto", { metodo: "DELETE" });
      setFoto(null);
      await alGuardar();
    } catch (err) {
      setAvisoFoto({ tipo: "error", texto: mensaje(err, "No se pudo quitar la foto.") });
    }
  };

  return (
    <Seccion titulo="Perfil público" ayuda="Lo que ven las demás personas.">
      <div className="panel-cuenta__foto">
        <Avatar nombre={visible || yo.nombre_visible} foto={foto} grande />
        <div className="panel-cuenta__foto-acciones">
          <label className="boton boton--borde boton--pequeno">
            {subiendo ? "Subiendo…" : foto ? "Cambiar foto" : "Subir foto"}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="oculto-visual" disabled={subiendo}
              onChange={(e) => { subir(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
          {foto && <button type="button" className="boton-texto" onClick={quitar}>Quitar foto</button>}
          <small className="tenue">JPG, PNG o WebP, hasta 2 MB. Se recorta en cuadrado y se le quitan los metadatos.</small>
        </div>
      </div>
      <Mensaje aviso={avisoFoto} />
      <form onSubmit={guardar} className="panel-cuenta__campos">
        <label className="campo-cuenta">
          <span>Nombre visible</span>
          <input value={visible} onChange={(e) => setVisible(e.target.value)} maxLength={60} required />
        </label>
        <label className="campo-cuenta">
          <span>Nombre de usuario</span>
          <span className="campo__prefijo"><span aria-hidden="true">@</span>
            <input value={nombre} onChange={(e) => setNombre(e.target.value.toLowerCase())} maxLength={30} required
              aria-describedby="estado-nombre" autoComplete="username" />
          </span>
          <small id="estado-nombre" className={`campo__estado campo__estado--${disponibilidad}`} aria-live="polite">
            {TEXTO_NOMBRE[disponibilidad]}{disponibilidad === "disponible" && " Tu nombre anterior seguirá llevando a tu perfil. Puedes cambiarlo una vez cada 30 días."}
          </small>
        </label>
        <label className="campo-cuenta">
          <span>Biografía</span>
          <textarea value={bio} onChange={(e) => setBio(e.target.value)} maxLength={MAX_BIO} rows={3}
            placeholder="Quién eres, de qué te interesa hablar." aria-describedby="cuenta-bio" />
          <small id="cuenta-bio" className="tenue cifra">{bio.length} / {MAX_BIO}</small>
        </label>
        <Mensaje aviso={aviso} />
        <button className="boton" disabled={!cambios || !nombreValido || enviando}>{enviando ? "Guardando…" : "Guardar cambios"}</button>
      </form>
    </Seccion>
  );
}

function Correo({ actual, alGuardar }: { actual: string; alGuardar: (correo: string) => void }) {
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [aviso, setAviso] = useState<Aviso>(null);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setAviso(null);
    try {
      const r = await api<{ correo: string }>("/social/v1/yo/correo", { metodo: "PUT", cuerpo: { correo, clave_actual: clave } });
      alGuardar(r.correo);
      setCorreo(""); setClave("");
      setAviso({ tipo: "ok", texto: "Correo actualizado." });
    } catch (err) {
      setAviso({ tipo: "error", texto: mensaje(err, "No se pudo cambiar el correo.") });
      setClave("");
    }
  };
  return (
    <Seccion titulo="Correo" ayuda={`Actual: ${actual}. Solo tú lo ves.`}>
      <form onSubmit={enviar} className="panel-cuenta__campos">
        <label className="campo-cuenta"><span>Nuevo correo</span>
          <input type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} autoComplete="email" required /></label>
        <label className="campo-cuenta"><span>Contraseña actual</span>
          <input type="password" value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="current-password" required /></label>
        <Mensaje aviso={aviso} />
        <button className="boton boton--borde" disabled={!correo || !clave}>Cambiar correo</button>
      </form>
    </Seccion>
  );
}

function Clave() {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [aviso, setAviso] = useState<Aviso>(null);
  const f = fuerza(nueva);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setAviso(null);
    try {
      const r = await api<{ sesiones_cerradas: number }>("/social/v1/yo/clave", { metodo: "PUT", cuerpo: { clave_actual: actual, clave_nueva: nueva } });
      setActual(""); setNueva("");
      setAviso({ tipo: "ok", texto: r.sesiones_cerradas
        ? `Contraseña actualizada. Se cerraron ${r.sesiones_cerradas === 1 ? "1 sesión" : `${r.sesiones_cerradas} sesiones`} en otros dispositivos.`
        : "Contraseña actualizada." });
    } catch (err) {
      setAviso({ tipo: "error", texto: mensaje(err, "No se pudo cambiar la contraseña.") });
      setActual("");
    }
  };
  return (
    <Seccion titulo="Contraseña" ayuda="Al cambiarla se cierran tus sesiones en otros dispositivos; esta sigue abierta.">
      <form onSubmit={enviar} className="panel-cuenta__campos">
        <label className="campo-cuenta"><span>Contraseña actual</span>
          <input type="password" value={actual} onChange={(e) => setActual(e.target.value)} autoComplete="current-password" required /></label>
        <label className="campo-cuenta"><span>Nueva contraseña</span>
          <input type="password" value={nueva} onChange={(e) => setNueva(e.target.value)} minLength={8} autoComplete="new-password" required /></label>
        {nueva && (
          <div className="fuerza" aria-live="polite">
            <span className="fuerza__barras">{[1, 2, 3, 4].map((n) => <i key={n} className={n <= f.nivel ? "activa" : ""} />)}</span>
            <small>{f.texto}</small>
          </div>
        )}
        <Mensaje aviso={aviso} />
        <button className="boton boton--borde" disabled={!actual || nueva.length < 8}>Cambiar contraseña</button>
      </form>
    </Seccion>
  );
}

function Desactivar({ alTerminar }: { alTerminar: () => void }) {
  const [clave, setClave] = useState("");
  const [seguro, setSeguro] = useState(false);
  const [aviso, setAviso] = useState<Aviso>(null);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setAviso(null);
    try {
      await api("/social/v1/yo/desactivacion", { metodo: "POST", cuerpo: { clave_actual: clave } });
      alTerminar();
    } catch (err) {
      setAviso({ tipo: "error", texto: mensaje(err, "No se pudo desactivar la cuenta.") });
      setClave("");
    }
  };
  return (
    <Seccion titulo="Desactivar la cuenta"
      ayuda="Tu cuenta deja de estar activa y se cierran todas tus sesiones. Tus publicaciones se conservan para que las conversaciones de otras personas no queden incompletas. No se puede deshacer desde la aplicación.">
      <form onSubmit={enviar} className="panel-cuenta__campos">
        <label className="campo-cuenta"><span>Contraseña actual</span>
          <input type="password" value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="current-password" required /></label>
        <label className="casilla">
          <input type="checkbox" checked={seguro} onChange={(e) => setSeguro(e.target.checked)} />
          <span>Entiendo que no podré volver a entrar con esta cuenta.</span>
        </label>
        <Mensaje aviso={aviso} />
        <button className="boton boton--peligro" disabled={!clave || !seguro}>Desactivar mi cuenta</button>
      </form>
    </Seccion>
  );
}
