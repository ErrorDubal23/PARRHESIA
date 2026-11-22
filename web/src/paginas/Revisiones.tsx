import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, cifra, ErrorApi, INDICADOR, periodo } from "../api";

interface Pendiente { id: string; texto_citado: string; indicador: string | null; periodo: string | null; valor_dicho: string | null;
  consenso: string | null; publicacion_id: string | null; creado_en: string }

export function Revisiones() {
  const [pendientes, setPendientes] = useState<Pendiente[] | null>(null);
  useEffect(() => { api<{ pendientes: Pendiente[] }>("/verificacion/v1/revisiones/pendientes").then((r) => setPendientes(r.pendientes)).catch(() => setPendientes([])); }, []);
  return (
    <>
      <h1 className="titulo-seccion">Revisiones</h1>
      <p className="tenue intro">Cifras que requieren revisión humana antes de mostrar una conclusión, por ejemplo cuando las dos lecturas automáticas no coinciden.</p>
      {pendientes?.length === 0 && <p className="tenue">No hay nada pendiente.</p>}
      <ul className="articulos">
        {pendientes?.map((p) => (
          <li key={p.id} className="tarjeta revision">
            <blockquote>«{p.texto_citado}»</blockquote>
            <p className="tenue">{INDICADOR[p.indicador ?? ""] ?? "—"} · {periodo(p.periodo)} · cifra dicha {cifra(p.valor_dicho)}
              {p.consenso === "difieren" && " · los lectores no coincidieron"}</p>
            {p.publicacion_id && <Link to={`/publicacion/${p.publicacion_id}`} className="enlace-suave">Ver la publicación</Link>}
          </li>
        ))}
      </ul>
      <PropuestasFigura />
    </>
  );
}

interface Propuesta { id: string; nombre_completo: string; cargo: string; url_fuente: string; nota: string | null; creada_en: string;
  propuesta_por: string; parecidas: { id: string; nombre_completo: string; cargo: string | null }[] }

/** Figuras propuestas por usuarios: aceptar crea la ficha; rechazar exige un motivo. */
function PropuestasFigura() {
  const [lista, setLista] = useState<Propuesta[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cargar = () => { api<{ propuestas: Propuesta[] }>("/social/v1/propuestas-figura").then((r) => setLista(r.propuestas)).catch(() => setLista([])); };
  useEffect(cargar, []);
  const resolver = async (p: Propuesta, aceptar: boolean) => {
    const motivo = aceptar ? null : prompt(`Motivo para rechazar la propuesta de ${p.nombre_completo}:`);
    if (!aceptar && !motivo) return;
    setError(null);
    try { await api(`/social/v1/propuestas-figura/${p.id}/resolucion`, { metodo: "POST", cuerpo: { aceptar, motivo } }); cargar(); }
    catch (e) { setError(e instanceof ErrorApi ? e.message : "No se pudo resolver la propuesta."); }
  };
  return (
    <>
      <h2 className="subtitulo revisiones__seccion">Figuras públicas propuestas</h2>
      {error && <p className="aviso" role="alert">{error}</p>}
      {lista?.length === 0 && <p className="tenue">No hay propuestas pendientes.</p>}
      <ul className="articulos">
        {lista?.map((p) => (
          <li key={p.id} className="tarjeta revision">
            <p><strong>{p.nombre_completo}</strong> · {p.cargo}</p>
            <p className="tenue">Propuesta por @{p.propuesta_por} · <a href={p.url_fuente} target="_blank" rel="noopener noreferrer" className="marca-texto">fuente del cargo</a></p>
            {p.nota && <p className="tenue">«{p.nota}»</p>}
            {p.parecidas.length > 0 && <p className="aviso">Fichas parecidas: {p.parecidas.map((x) => x.nombre_completo).join(", ")}. Revisa que no sea la misma persona.</p>}
            <div className="integrantes__acciones">
              <button className="boton boton--pequeno" onClick={() => resolver(p, true)}>Aceptar y crear ficha</button>
              <button className="boton-texto" onClick={() => resolver(p, false)}>Rechazar</button>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
