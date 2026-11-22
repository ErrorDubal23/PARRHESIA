// Genera los archivos de marca desde la fuente única web/src/marca.ts: `npm run marca`.
// Salidas: web/public/logo.svg, web/public/favicon.svg y diagramas/marca/*.svg.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const fuente = readFileSync(join(web, "src/marca.ts"), "utf8");
const leer = (nombre) => {
  const m = fuente.match(new RegExp(`export const ${nombre} =([^;]+);`));
  if (!m) throw new Error(`No encuentro ${nombre} en marca.ts`);
  return m[1];
};
const ALA = [...leer("ALA").matchAll(/"([^"]*)"/g)].map((x) => x[1]).join("");
const ANCHO = Number(leer("ANCHO"));
const ALTO = Number(leer("ALTO"));
const COLORES = Object.fromEntries([...leer("COLORES").matchAll(/(\w+): "(#[0-9A-Fa-f]{6})"/g)].map((x) => [x[1], x[2]]));
const ESPEJO = `translate(${ANCHO} 0) scale(-1 1)`;
const nota = "<!-- Generado por web/scripts/generar_marca.mjs desde web/src/marca.ts. No editar a mano. -->";

const simbolo = (relleno) =>
  `<path id="ala" fill="${relleno}" d="${ALA}"/>\n  <use href="#ala" transform="${ESPEJO}"/>`;

const logo = (relleno) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${ANCHO} ${ALTO}" role="img" aria-label="Parrhesia">
  ${nota}
  ${simbolo(relleno)}
</svg>
`;

// Ícono cuadrado: el símbolo ocupa el 66 % del ancho, centrado ópticamente (un poco arriba).
const icono = (fondo, relleno) => {
  const lado = 120, ancho = lado * 0.66, escala = ancho / ANCHO;
  const x = (lado - ancho) / 2, y = (lado - ALTO * escala) / 2 - 1.5;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${lado} ${lado}">
  ${nota}
  <rect width="${lado}" height="${lado}" rx="28" fill="${fondo}"/>
  <g transform="translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(${escala.toFixed(4)})">
    ${simbolo(relleno).replace("\n  ", "\n    ")}
  </g>
</svg>
`;
};

// El logo suelto se adapta al tema del sistema (útil al abrirlo directamente).
const logoAdaptable = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${ANCHO} ${ALTO}" role="img" aria-label="Parrhesia">
  ${nota}
  <style>path, use { fill: ${COLORES.tinta}; } @media (prefers-color-scheme: dark) { path, use { fill: ${COLORES.crema}; } }</style>
  <path id="ala" d="${ALA}"/>
  <use href="#ala" transform="${ESPEJO}"/>
</svg>
`;

const salidas = {
  "public/logo.svg": logoAdaptable,
  "public/favicon.svg": icono(COLORES.arena, COLORES.tinta),
  "../diagramas/marca/logo_negro.svg": logo(COLORES.tinta),
  "../diagramas/marca/logo_crema.svg": logo(COLORES.crema),
  "../diagramas/marca/icono_app.svg": icono(COLORES.arena, COLORES.tinta),
  "../diagramas/marca/icono_app_oscuro.svg": icono(COLORES.tinta, COLORES.crema),
};
for (const [ruta, contenido] of Object.entries(salidas)) {
  writeFileSync(join(web, ruta), contenido);
  console.log("escrito", ruta);
}
