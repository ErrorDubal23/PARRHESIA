/* Fondo de la app: pliegues de seda en los tonos del tema, a distintas distancias.
   Cada pliegue es un plano: los lejanos van más tenues y se mueven menos al hacer scroll (paralaje), los
   cercanos más presentes y más rápidos; un velo oscurece apenas los bordes para que el fondo quede atrás.
   El paralaje lo mueve el navegador con una animación ligada al scroll (profundidad.css), sin JavaScript.
   Dentro de cada plano el pliegue ondula muy despacio. Los colores salen de --seda-luz y --seda-sombra.
   Es decorativo: aria-hidden, y quieto si la persona pidió reducir el movimiento. */
const PLIEGUES = [
  // Barrido amplio que baja desde la esquina superior derecha (lejano).
  { clase: "seda__capa--1", distancia: "lejos", d: "M760 -40 C 980 120 1080 260 1500 220 L1500 -40 Z M1500 220 C 1180 300 1020 520 1180 960 L1500 960 Z", luz: true },
  // Ola media que cruza la parte baja (lejana).
  { clase: "seda__capa--2", distancia: "lejos", d: "M-60 760 C 260 640 560 700 820 820 C 1020 910 1260 860 1500 700 L1500 960 L-60 960 Z", luz: false },
  // Pliegue estrecho a la derecha, el que da la sensación de tela doblada (cerca).
  { clase: "seda__capa--3", distancia: "cerca", d: "M1100 -40 C 1060 200 1240 380 1500 420 L1500 -40 Z", luz: false },
  // Brillo suave en la diagonal (cerca).
  { clase: "seda__capa--4", distancia: "cerca", d: "M600 960 C 820 640 1120 520 1500 500 L1500 600 C 1180 640 920 760 760 960 Z", luz: true },
];

export function FondoSeda() {
  return (
    <div className="seda" aria-hidden="true">
      {PLIEGUES.map((p, i) => (
        <div key={i} className={`seda__plano seda__plano--${p.distancia}`}>
          <svg className={`seda__capa ${p.clase}`} viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
            <defs>
              <linearGradient id={`seda-g${i}`} x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor={p.luz ? "var(--seda-luz)" : "var(--seda-sombra)"} stopOpacity="0" />
                <stop offset="0.45" stopColor={p.luz ? "var(--seda-luz)" : "var(--seda-sombra)"} stopOpacity="0.95" />
                <stop offset="1" stopColor={p.luz ? "var(--seda-luz)" : "var(--seda-sombra)"} stopOpacity="0.35" />
              </linearGradient>
            </defs>
            <path d={p.d} fill={`url(#seda-g${i})`} />
          </svg>
        </div>
      ))}
      <div className="seda__velo" />
    </div>
  );
}
