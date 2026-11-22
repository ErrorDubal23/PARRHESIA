// La conclusión de una verificación. Nunca "verdadero/falso" ni verde/rojo: cada conclusión
// tiene un glifo geométrico propio y un texto neutral que describe lo que pasa con el dato.
import type { Conclusion, EstadoVerificacion } from "../tipos";

export const CONCLUSIONES: Record<Conclusion, { titulo: string; frase: string }> = {
  se_sostiene: { titulo: "Se sostiene", frase: "La cifra coincide con el dato oficial." },
  se_debilita: { titulo: "Se debilita", frase: "El dato oficial no respalda la cifra tal como se dijo." },
  se_invierte: { titulo: "Se invierte", frase: "El dato oficial va en la dirección contraria." },
  sin_dato_comparable: { titulo: "Sin dato comparable", frase: "No hay un dato oficial registrado con el que se pueda comparar." },
};

export function Glifo({ tipo, tamano = 18 }: { tipo: Conclusion | "pendiente" | "revision"; tamano?: number }) {
  const t = tamano;
  if (tipo === "pendiente") {
    return <span className="cargando" aria-hidden="true"><i /><i /><i /></span>;
  }
  return (
    <svg width={t} height={t} viewBox="0 0 20 20" aria-hidden="true" className={`glifo glifo--${tipo}`}>
      {tipo === "se_sostiene" && <circle cx="10" cy="10" r="7.5" fill="currentColor" />}
      {tipo === "se_debilita" && (
        <>
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path d="M10 3a7 7 0 0 1 0 14z" fill="currentColor" />
        </>
      )}
      {tipo === "se_invierte" && (
        <path d="M6 3v12m0 0-3-3m3 3 3-3M14 17V5m0 0-3 3m3-3 3 3" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {tipo === "sin_dato_comparable" && (
        <>
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray="2.6 2.2" />
        </>
      )}
      {tipo === "revision" && (
        <path d="M4 10.5 8 14l8-8.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray="3 2.4" strokeLinecap="round" />
      )}
    </svg>
  );
}

/** Franja que acompaña a una publicación. Forma de ficha con la esquina doblada (evidencia). */
export function Veredicto({ estado, conclusion, resumen }: {
  estado: EstadoVerificacion;
  conclusion?: Conclusion | null;
  resumen?: string | null;
}) {
  if (estado === "sin_cifras") return null;
  if (estado === "pendiente") {
    return (
      <div className="veredicto veredicto--pendiente">
        <Glifo tipo="pendiente" />
        <span>Uniendo la cifra a su dato oficial…</span>
      </div>
    );
  }
  if (estado === "requiere_revision" || !conclusion) {
    return (
      <div className="veredicto veredicto--revision">
        <Glifo tipo="revision" />
        <strong>En revisión</strong>
        <span className="veredicto__texto">Una persona del equipo de verificación revisa esta cifra.</span>
      </div>
    );
  }
  return (
    <div className={`veredicto veredicto--${conclusion}`}>
      <Glifo tipo={conclusion} />
      <strong>{CONCLUSIONES[conclusion].titulo}</strong>
      <span className="veredicto__texto">{resumen ?? CONCLUSIONES[conclusion].frase}</span>
    </div>
  );
}
