// Página de "no está" (404) o "no es para ti" (403). Una cara hecha con el mismo número: los "4" (o el
// "3") son los ojos y el "0" la nariz, con la mariposa del logo posada encima. Las animaciones son la
// expresión: la boca se dibuja al llegar, los ojos parpadean y la mariposa aletea una vez.
// Quieta si se pide menos movimiento.
import { useId, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { ErrorApi } from "../api";
import { ALA, ALTO, ANCHO, EJE, ESPEJO } from "../marca";

export function Cara({ codigo = "404" }: { codigo?: "404" | "403" }) {
  const expresion = codigo === "403" ? "seria" : "triste";
  const ala = useId();
  // Boca en dos mitades (se dibujan desde las comisuras); triste baja en los extremos, seria es recta.
  const boca = expresion === "triste"
    ? ["M 0 30 C 0 30 40 0 95 0", "M 95 0 C 150 0 190 30 190 30"]
    : ["M 0 12 L 95 12", "M 95 12 L 190 12"];
  return (
    <svg className="cara" viewBox="0 0 320 380" role="img" aria-label={`Una cara formada por el número ${codigo}`}>
      {/* La mariposa del logo, posada sobre el 0: aletea una vez al llegar (misma animación del logo). */}
      <svg className="logo logo--al-pasar cara__mariposa" x="125" y="44" width="70" height={(70 * ALTO) / ANCHO}
        viewBox={`0 0 ${ANCHO} ${ALTO}`} style={{ "--eje": `${EJE}px` } as CSSProperties} aria-hidden="true">
        <defs><path id={ala} d={ALA} /></defs>
        <g className="logo__ala"><use href={`#${ala}`} fill="currentColor" /></g>
        <g className="logo__ala"><use href={`#${ala}`} transform={ESPEJO} fill="currentColor" /></g>
      </svg>
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="22">
        <g transform="translate(0 112.5)">
          <g transform="translate(15 0)">
            <polyline points="37,0 0,120 75,120" />
            <polyline className="cara__pupila" points="55,120 55,155" strokeDasharray="35 35" />
          </g>
          <g transform="translate(230 0)">
            {codigo === "403"
              ? <path d="M 8 0 H 72 L 34 62 C 84 58 92 150 8 152" />
              : <><polyline points="37,0 0,120 75,120" />
                <polyline className="cara__pupila" points="55,120 55,155" strokeDasharray="35 35" /></>}
          </g>
        </g>
        <rect x="132.5" y="112.5" width="55" height="155" rx="6" />
        <g transform="translate(65 324)" strokeDasharray="102 102">
          <path className="cara__boca" d={boca[0]} />
          <path className="cara__boca cara__boca--der" d={boca[1]} />
        </g>
      </g>
    </svg>
  );
}

export function NoEncontrado({
  codigo = "404",
  titulo = "Esta página no está en el registro.",
  texto = "La dirección no lleva a ninguna publicación, perfil ni dato oficial. Puede que haya cambiado o que nunca haya existido.",
}: { codigo?: "404" | "403"; titulo?: string; texto?: string }) {
  return (
    <section className="no-encontrado" aria-labelledby="titulo-no-encontrado">
      <Cara codigo={codigo} />
      <div className="no-encontrado__texto">
        <p className="sello">{codigo === "403" ? "Acceso restringido" : "Error 404"}</p>
        <h1 id="titulo-no-encontrado">{titulo}</h1>
        <p className="tenue">{texto}</p>
        <div className="no-encontrado__acciones">
          <Link to="/" className="boton">Volver al inicio</Link>
          <Link to="/buscar" className="boton boton--borde">Buscar</Link>
        </div>
      </div>
    </section>
  );
}

/** Lo que falló al cargar algo: 404 muestra la cara; cualquier otro error, un aviso claro (nunca una espera eterna). */
export interface Fallo { estado: number; mensaje: string }
export const comoFallo = (e: unknown): Fallo => ({
  estado: e instanceof ErrorApi ? e.estado : 0,
  mensaje: e instanceof ErrorApi ? e.message : "No se pudo cargar. Revisa tu conexión e inténtalo de nuevo.",
});

export function MostrarFallo({ fallo, titulo }: { fallo: Fallo; titulo: string }) {
  if (fallo.estado === 404 || fallo.estado === 422) return <NoEncontrado titulo={titulo} />; // un id mal formado tampoco existe
  return <p className="aviso" role="alert">{fallo.mensaje}</p>;
}
