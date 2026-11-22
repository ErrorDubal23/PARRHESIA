// Íconos propios, trazo de 1.8 px, para que todo hable el mismo idioma visual.
import { useId, type CSSProperties, type SVGProps } from "react";
import { ALA, ALTO, ANCHO, EJE, ESPEJO } from "../marca";

const base = (props: SVGProps<SVGSVGElement>) => ({
  width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, ...props,
});

/**
 * Símbolo de Parrhesia. `aleteo`: "siempre" (pantalla de acceso), "al-pasar" (barra lateral) o nada.
 * El aleteo pliega las dos alas a la vez sobre el eje central y vuelve, con una pausa larga; si el
 * sistema pide menos movimiento, queda quieto. Ver la animación en estilos/base.css (.logo).
 */
export function Logo({ tamano = 34, aleteo }: { tamano?: number; aleteo?: "siempre" | "al-pasar" }) {
  const id = useId();
  return (
    <svg className={`logo${aleteo ? ` logo--${aleteo}` : ""}`} width={tamano} height={(tamano * ALTO) / ANCHO}
      viewBox={`0 0 ${ANCHO} ${ALTO}`} aria-hidden="true" style={{ "--eje": `${EJE}px` } as CSSProperties}>
      <defs><path id={id} d={ALA} /></defs>
      <g className="logo__ala"><use href={`#${id}`} fill="currentColor" /></g>
      <g className="logo__ala"><use href={`#${id}`} fill="currentColor" transform={ESPEJO} /></g>
    </svg>
  );
}

export const Inicio = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" /></svg>;
export const Temas = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 5h11v14H6a1 1 0 0 1-1-1zM16 9h3v9a1 1 0 0 1-1 1h-2M8 9h5M8 12h5M8 15h3" /></svg>;
export const Tendencias = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 17 9 11l4 4 7-8M15 7h5v5" /></svg>;
export const Figuras = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" /></svg>;
export const Comunidades = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="8" cy="9" r="3" /><circle cx="16" cy="9" r="3" /><path d="M3 19c.6-2.8 2.6-4.3 5-4.3s4.4 1.5 5 4.3M11 19c.6-2.8 2.6-4.3 5-4.3s4.4 1.5 5 4.3" /></svg>;
export const Datos = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 20h16M7 16v-5M12 16V6M17 16v-8" /></svg>;
export const Perfil = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><rect x="4" y="4" width="16" height="16" rx="4" /><circle cx="12" cy="10" r="2.5" /><path d="M8 17c.8-1.8 2.2-2.7 4-2.7s3.2.9 4 2.7" /></svg>;
export const Revisiones = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M9 4h6l1 2h3v14H5V6h3zM9 13l2 2 4-4" /></svg>;
export const Lapiz = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 20l4-1L19 8a2.1 2.1 0 0 0-3-3L5 16zM14 7l3 3" /></svg>;
export const Buscar = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>;
export const Responder = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M20 12a7.5 7.5 0 0 1-11 6.6L4 20l1.4-4.4A7.5 7.5 0 1 1 20 12z" /></svg>;
export const Compartir = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M7 7h11l-3-3M17 17H6l3 3M18 7v4M6 17v-4" /></svg>;
export const MeGusta = ({ lleno, ...p }: SVGProps<SVGSVGElement> & { lleno?: boolean }) => (
  <svg {...base(p)} fill={lleno ? "currentColor" : "none"}><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" /></svg>
);
export const Util = ({ lleno, ...p }: SVGProps<SVGSVGElement> & { lleno?: boolean }) => (
  <svg {...base(p)}><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.5.4.6.9.6 1.5V16h6v-.7c0-.6.2-1.1.6-1.5A6 6 0 0 0 12 3z" fill={lleno ? "currentColor" : "none"} /></svg>
);
export const Salir = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M14 5h4a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h9" /></svg>;
export const Volver = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M19 12H5m6-6-6 6 6 6" /></svg>;
export const Flecha = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="m9 6 6 6-6 6" /></svg>;
export const Enlace = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>;
