// Equipo (migración 0035): quién verifica, quién administra, y la bitácora de cada cambio de rol con su motivo.
// Es pública, como la bitácora de las figuras: el permiso de verificar tiene que ser tan visible como lo que se
// verifica. Solo un administrador ve el formulario, y aun así la base decide (motivo obligatorio y nunca dejar a
// Parrhesia sin administrador).
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ErrorApi, haceCuanto } from "../api";
import { Avatar } from "../componentes/Avatar";
import { useSesion } from "../sesion";

type Rol = "usuario" | "verificador" | "admin";
interface Miembro { nombre_usuario: string; nombre_visible: string; rol: Rol; desde: string | null; foto: string | null }
interface Cambio {
  id: number; nombre_usuario: string; nombre_visible: string; rol_anterior: Rol; rol_nuevo: Rol;
  actor: string | null; motivo: string; creado_en: string;
}
interface Datos { miembros: Miembro[]; bitacora: Cambio[] }

const NOMBRE: Record<Rol, string> = { usuario: "Usuario", verificador: "Verificador", admin: "Administrador" };
const QUE_HACE: Record<Exclude<Rol, "usuario">, string> = {
  verificador: "Registra figuras públicas y declaraciones con su fuente, resuelve propuestas y hace las revisiones humanas.",
  admin: "Todo lo del verificador; además asigna roles y puede retirar publicaciones. Siempre hay al menos uno.",
};

export function Equipo() {
  const { usuario } = useSesion();
  const [datos, setDatos] = useState<Datos | null>(null);
  const [form, setForm] = useState({ nombre_usuario: "", rol: "verificador" as Rol, motivo: "" });
  const [estado, setEstado] = useState<{ ok: boolean; texto: string } | null>(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { api<Datos>("/social/v1/equipo").then(setDatos).catch(() => setDatos({ miembros: [], bitacora: [] })); }, []);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setEstado(null);
    try {
      const r = await api<Datos>("/social/v1/equipo/roles", { metodo: "POST",
        cuerpo: { ...form, nombre_usuario: form.nombre_usuario.trim().replace(/^@/, "") } });
      setDatos(r);
      setEstado({ ok: true, texto: `@${form.nombre_usuario.replace(/^@/, "")} ahora es ${NOMBRE[form.rol].toLowerCase()}. Quedó en la bitácora.` });
      setForm({ nombre_usuario: "", rol: "verificador", motivo: "" });
    } catch (err) {
      setEstado({ ok: false, texto: err instanceof ErrorApi ? err.message : "No se pudo guardar. Revisa tu conexión." });
    } finally {
      setEnviando(false);
    }
  };

  return (
    <>
      <h1 className="titulo-seccion">Equipo</h1>
      <p className="tenue intro">Quién puede verificar y administrar, quién le dio ese permiso y por qué. Cada cambio queda
        en la bitácora pública y no se puede borrar.</p>

      <section className="tarjeta bloque equipo">
        <h2 className="subtitulo">Quiénes son</h2>
        {!datos && <span className="cargando"><i /><i /><i /></span>}
        <ul className="equipo__lista">
          {datos?.miembros.map((m) => (
            <li key={m.nombre_usuario}>
              <Link to={`/perfil/${m.nombre_usuario}`} className="equipo__persona">
                <Avatar nombre={m.nombre_visible} foto={m.foto} />
                <span><strong>{m.nombre_visible}</strong><small>@{m.nombre_usuario}</small></span>
              </Link>
              <span className={`equipo__rol equipo__rol--${m.rol}`}>{NOMBRE[m.rol]}</span>
            </li>
          ))}
        </ul>
        <dl className="equipo__permisos">
          {(Object.keys(QUE_HACE) as (keyof typeof QUE_HACE)[]).map((r) => (
            <div key={r}><dt>{NOMBRE[r]}</dt><dd>{QUE_HACE[r]}</dd></div>
          ))}
        </dl>
      </section>

      {usuario?.rol === "admin" && (
        <form className="tarjeta bloque equipo__form" onSubmit={enviar}>
          <h2 className="subtitulo">Cambiar el rol de una cuenta</h2>
          <div className="campos-dobles">
            <label className="campo-cuenta"><span>Nombre de usuario</span>
              <input value={form.nombre_usuario} onChange={(e) => setForm({ ...form, nombre_usuario: e.target.value })}
                placeholder="@usuario" required minLength={3} maxLength={31} autoComplete="off" />
            </label>
            <label className="campo-cuenta"><span>Nuevo rol</span>
              <select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value as Rol })}>
                <option value="verificador">Verificador</option>
                <option value="admin">Administrador</option>
                <option value="usuario">Usuario (quitar el rol)</option>
              </select>
            </label>
          </div>
          <label className="campo-cuenta"><span>Motivo (queda en la bitácora pública)</span>
            <textarea value={form.motivo} onChange={(e) => setForm({ ...form, motivo: e.target.value })} rows={2}
              minLength={10} maxLength={500} required placeholder="Por ejemplo: se suma al equipo de verificación de la universidad." />
          </label>
          {estado && <p className={estado.ok ? "panel-cuenta__ok" : "aviso"} role={estado.ok ? "status" : "alert"}>{estado.texto}</p>}
          <button className="boton" disabled={enviando}>{enviando ? "Guardando…" : "Guardar cambio"}</button>
        </form>
      )}

      <section className="tarjeta bloque">
        <h2 className="subtitulo">Bitácora de roles</h2>
        {datos?.bitacora.length === 0 && <p className="tenue">Todavía no hay cambios de rol.</p>}
        <ol className="bitacora">
          {datos?.bitacora.map((b) => (
            <li key={b.id}>
              <span>
                <strong>@{b.nombre_usuario}</strong>: {NOMBRE[b.rol_anterior]} → {NOMBRE[b.rol_nuevo]}
                <span className="tenue"> · {b.actor ? <>lo decidió @{b.actor}</> : "desde la consola del proyecto"}</span>
              </span>
              <span className="bitacora__motivo">Motivo: {b.motivo}</span>
              <time className="tenue" dateTime={b.creado_en}>{haceCuanto(b.creado_en)}</time>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
