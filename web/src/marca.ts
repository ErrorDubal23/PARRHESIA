// Fuente única del símbolo de Parrhesia (versión mariposa, 21 nov 2026). Todo lo demás sale de aquí:
// el componente <Logo>, el favicon, el ícono de app y los SVG de diagramas/marca
// (se regeneran con `npm run marca`). No se redibuja en ningún otro lugar.
//
// Dos "P" en espejo: el ojo de cada P se abre hacia el centro y su trazo inferior baja como el
// cuerpo de una mariposa. Ninguna mitad pesa más que la otra.

/** Ala izquierda; la derecha es su reflejo exacto sobre el eje central. */
export const ALA =
  "M0 0 L35.5 13.7 C40 15.5 43 20.7 43 25.7 L42.9 48.2 L35.4 29.8 C34.6 28.1 32.3 25.9 29.2 24.7 " +
  "L14.2 19.2 L14.4 27.6 L35.5 41.7 L40.1 53.5 L22.5 65.6 L22.3 46.4 L30.7 49 L6.4 35.4 " +
  "C3.3 33.7 0 30.3 0 26.4 Z";
export const ANCHO = 92.8;
export const ALTO = 65.6;
export const EJE = ANCHO / 2;
export const ESPEJO = `translate(${ANCHO} 0) scale(-1 1)`;

/** Paleta de la marca (la misma de la app). */
export const COLORES = { tinta: "#1E1E1E", crema: "#F7F3EC", arena: "#D9C6AD" };
