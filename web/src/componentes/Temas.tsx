// Piezas visuales de los temas del día, todas con datos reales de la API de temas:
// - Huella de cobertura: los medios registrados en anillo; encendidos los que cubren el tema.
// - Actividad: artículos del tema por tramo de 3 horas de su ventana.
// - Pila de temas de la columna derecha.
// Cobertura no es importancia ni veracidad: nada aquí ordena por relevancia ni califica.
import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { api, haceCuanto } from "../api";
import * as I from "./Iconos";

export interface TemaResumen {
  id: string; titulo: string; etiqueta: string; total_medios: number; total_articulos: number;
  ventana_inicio: string; ventana_fin: string;
  medios: { medio: string; articulos: number; primero: string }[];
  actividad: number[];
  imagen?: { url: string; autor: string; url_autor: string; url_foto: string; color: string | null } | null;
}

/** Anillo de medios registrados. El grupo de puntos gira despacio; el número del centro no. */
export function Huella({ registrados, cubren, total, tamano = 150 }: { registrados: string[]; cubren: string[]; total: number; tamano?: number }) {
  const lista = registrados.length ? registrados : cubren;
  const radio = 52;
  const etiqueta = `Lo cubren ${cubren.length} de ${lista.length} medios registrados: ${cubren.join(", ")}`;
  return (
    <svg className="huella" viewBox="0 0 140 140" width={tamano} height={tamano} role="img" aria-label={etiqueta}>
      <title>{etiqueta}</title>
      <g className="huella__anillo">
        <circle cx="70" cy="70" r={radio} className="huella__orbita" />
        {lista.map((m, i) => {
          const a = (i / lista.length) * Math.PI * 2 - Math.PI / 2;
          const encendido = cubren.includes(m);
          return <circle key={m} cx={70 + Math.cos(a) * radio} cy={70 + Math.sin(a) * radio} r={encendido ? 6.5 : 3}
            className={encendido ? "huella__medio huella__medio--cubre" : "huella__medio"} />;
        })}
      </g>
      <text x="70" y="74" textAnchor="middle" className="huella__total">{total}</text>
      <text x="70" y="92" textAnchor="middle" className="huella__rotulo">medios</text>
    </svg>
  );
}

/** Barras de actividad: artículos por tramo de 3 horas. */
export function Actividad({ tramos }: { tramos: number[] }) {
  const max = Math.max(1, ...tramos);
  const total = tramos.reduce((s, n) => s + n, 0);
  return (
    <span className="actividad" role="img" aria-label={`Artículos por tramo de 3 horas en las últimas 24 horas: ${tramos.join(", ")}`}>
      {tramos.map((n, i) => <i key={i} style={{ height: `${n ? 18 + (n / max) * 82 : 6}%` }} className={n ? "" : "actividad__nula"} title={`${n} de ${total}`} />)}
    </span>
  );
}

const capitalizar = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/**
 * Pila de temas para la columna derecha: tarjetas apiladas, una abierta a la vez. Cada elemento visual
 * dice algo del tema: el anillo, qué medios registrados lo cubren; las barras, cuándo se publicó; el
 * tema abierto se distingue por su fondo. La única animación es la de abrir y cerrar.
 */
export function PilaTemas() {
  const [datos, setDatos] = useState<{ temas: TemaResumen[]; medios_registrados: string[] } | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  const base = useId();

  useEffect(() => {
    api<typeof datos>("/temas/v1/temas")
      .then((d) => { setDatos(d); setAbierto(d?.temas[0]?.id ?? null); })
      .catch(() => setDatos({ temas: [], medios_registrados: [] }));
  }, []);

  return (
    <section className="pila-temas" aria-label="Temas del día">
      <div className="bloque__cabecera">
        <h2 className="subtitulo">Temas del día</h2>
        <Link to="/temas" className="enlace-suave">Ver todos <I.Flecha width={14} /></Link>
      </div>
      {!datos && <span className="cargando"><i /><i /><i /></span>}
      {datos?.temas.length === 0 && <p className="tenue">Aún no hay temas en esta ventana.</p>}
      <ol className="pila-temas__lista">
        {datos?.temas.map((t, i) => {
          const abierta = abierto === t.id;
          const id = `${base}-${i}`;
          const cubren = t.medios.map((m) => m.medio);
          return (
            <li key={t.id} className={`pila-tema${abierta ? " pila-tema--abierta" : ""}`} style={{ zIndex: abierta ? datos.temas.length + 1 : datos.temas.length - i }}>
              <h3 className="pila-tema__cabecera">
                <button type="button" aria-expanded={abierta} aria-controls={`${id}-cuerpo`} id={`${id}-boton`}
                  onClick={() => setAbierto(abierta ? null : t.id)}>
                  <span className="pila-tema__titulo">{capitalizar(t.titulo)}</span>
                  <span className="pila-tema__conteo"><span className="cifra">{t.total_medios}</span> medios · <span className="cifra">{t.total_articulos}</span> artículos</span>
                  <svg className="pila-tema__flecha" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" /></svg>
                </button>
              </h3>
              <div className="pila-tema__cuerpo" id={`${id}-cuerpo`} role="region" aria-labelledby={`${id}-boton`}>
                <div className="pila-tema__interior">
                  <span className="pila-tema__etiqueta">#{t.etiqueta}</span>
                  <div className="pila-tema__cobertura">
                    <Huella registrados={datos.medios_registrados} cubren={cubren} total={t.total_medios} tamano={92} />
                    <ul className="pila-tema__medios" aria-label="Medios que lo cubren">
                      {t.medios.map((m) => <li key={m.medio}>{m.medio} <span className="cifra">{m.articulos}</span></li>)}
                    </ul>
                  </div>
                  <div className="pila-tema__actividad">
                    <Actividad tramos={t.actividad} />
                    <span>Artículos cada 3 horas{t.medios[0] ? ` · desde hace ${haceCuanto(t.medios[0].primero)}` : ""}</span>
                  </div>
                  <Link to={`/temas/${t.id}`} className="pila-tema__ir">Leer el tema <I.Flecha width={14} /></Link>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** Temas del día en la columna derecha: una tarjeta con imagen por tema, con flechas y puntos (sin pasar sola). */
export function CarruselTemas() {
  const [temas, setTemas] = useState<TemaResumen[] | null>(null);
  const [actual, setActual] = useState(0);
  useEffect(() => {
    api<{ temas: TemaResumen[] }>("/temas/v1/temas").then((d) => setTemas(d.temas)).catch(() => setTemas([]));
  }, []);
  const total = temas?.length ?? 0;
  const ir = (paso: number) => setActual((a) => (a + paso + total) % total);
  const t = temas?.[actual];
  return (
    <section className="carrusel-temas tarjeta" aria-label="Temas del día" aria-roledescription="carrusel">
      <div className="bloque__cabecera">
        <h2 className="subtitulo">Temas del día</h2>
        <Link to="/temas" className="enlace-suave">Ver todos <I.Flecha width={14} /></Link>
      </div>
      {!temas && <span className="cargando"><i /><i /><i /></span>}
      {temas?.length === 0 && <p className="tenue">Aún no hay temas en esta ventana.</p>}
      {t && (
        <>
          <article className="tema-portada" style={{ backgroundColor: t.imagen?.color ?? undefined }}
            aria-roledescription="diapositiva" aria-label={`${actual + 1} de ${total}`}>
            {t.imagen && <img src={t.imagen.url} alt="" loading="lazy" decoding="async" />}
            <div className="tema-portada__velo" />
            {total > 1 && (
              <>
                <button className="tema-portada__flecha tema-portada__flecha--antes" onClick={() => ir(-1)} aria-label="Tema anterior">
                  <svg viewBox="0 0 12 12" width="14" height="14" aria-hidden="true"><path d="M7.5 3 4.5 6l3 3" /></svg>
                </button>
                <button className="tema-portada__flecha tema-portada__flecha--despues" onClick={() => ir(1)} aria-label="Tema siguiente">
                  <svg viewBox="0 0 12 12" width="14" height="14" aria-hidden="true"><path d="M4.5 3l3 3-3 3" /></svg>
                </button>
              </>
            )}
            <Link to={`/temas/${t.id}`} className="tema-portada__texto">
              <h3>{capitalizar(t.titulo)}</h3>
              <span><span className="cifra">{t.total_medios}</span> medios · <span className="cifra">{t.total_articulos}</span> artículos</span>
            </Link>
            {t.imagen && (
              <small className="tema-portada__credito">
                Foto: <a href={t.imagen.url_autor} target="_blank" rel="noreferrer noopener">{t.imagen.autor}</a> en{" "}
                <a href={t.imagen.url_foto} target="_blank" rel="noreferrer noopener">Unsplash</a>
              </small>
            )}
          </article>
          {total > 1 && (
            <div className="carrusel-temas__puntos" role="tablist" aria-label="Elegir tema">
              {temas!.map((x, i) => (
                <button key={x.id} role="tab" aria-selected={i === actual} aria-label={capitalizar(x.titulo)} onClick={() => setActual(i)} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
