/* Fondo de la app, copiado de la referencia visual del 23 nov 2026: dos piezas fijas a la ventana.
   - Grupo derecho, pegado al borde: una banda que entra por arriba, la esquina, una tira que baja junto a la
     columna derecha hasta un tercio de la altura y un gran trazo claro que sigue hasta abajo.
   - A la izquierda, un lóbulo grande que nace en el borde y pasa por detrás del menú, y otra forma de contraste
     en la esquina inferior.
   Cada pieza usa su propio color por tema (--forma-banda, --forma-esquina, --forma-tira, --forma-lado,
   --forma-izq en base.css): en claro pizarra y arena; en oscuro se intercambian, como en la referencia.
   Se mueven muy poco (flotan unos píxeles) y nada si se pidió reducir el movimiento. Decorativo: aria-hidden. */
export function FondoSeda() {
  return (
    <div className="seda" aria-hidden="true">
      {/* Toque nacional: palmas de cera y granos de café en acuarela, muy desvanecidos detrás del contenido. */}
      <div className="fondo-nacional" />
      {/* Coordenadas: x = 0 es 400 px antes del borde derecho; y = 0 es el borde de arriba (alto de 950). */}
      <svg className="forma forma--derecha" viewBox="0 0 400 950" preserveAspectRatio="xMaxYMin slice">
        <path className="forma__lado" d="M400 290 C345 330 318 420 328 520 C338 640 352 780 372 950 L400 950 Z" />
        <path className="forma__banda" d="M35 0 C90 45 200 75 290 100 C320 108 345 112 365 114 L400 116 L400 0 Z" />
        <path className="forma__tira" d="M316 104 C334 140 331 190 335 232 C341 286 368 322 400 346 L400 96 C368 101 340 103 316 104 Z" />
        <path className="forma__esquina" d="M255 0 C268 45 300 78 345 95 C365 103 385 116 400 128 L400 0 Z" />
      </svg>
      {/* Izquierda: un lóbulo grande que nace en el borde de la pantalla y pasa por detrás del menú (el vidrio
          del menú lo desenfoca), y una forma de contraste más pequeña en la esquina inferior. */}
      <svg className="forma forma--izquierda" viewBox="0 0 330 360" preserveAspectRatio="xMinYMin meet">
        <path className="forma__izq" d="M0 22 C70 0 205 6 280 82 C338 140 322 222 268 276 C226 318 168 342 116 358 C92 322 50 304 0 300 Z" />
      </svg>
      <svg className="forma forma--rincon" viewBox="0 0 240 200" preserveAspectRatio="xMinYMax meet">
        <path className="forma__rincon" d="M0 52 C66 30 148 62 190 122 C212 154 220 182 214 200 L0 200 Z" />
      </svg>
    </div>
  );
}
