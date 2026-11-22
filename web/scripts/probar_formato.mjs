// Comprueba que formato.ts quita las marcas igual que util.texto_plano (los mismos casos que
// tests/test_formato.py). Uso: node --experimental-strip-types web/scripts/probar_formato.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const { textoPlano } = await import(join(aqui, "../src/formato.ts"));
const casos = JSON.parse(readFileSync(join(aqui, "../../tests/datos/casos_formato.json"), "utf8"));
let fallos = 0;
for (const { texto, plano } of casos) {
  const obtenido = textoPlano(texto);
  if (obtenido !== plano) { fallos++; console.error(`FALLA: ${JSON.stringify(texto)}\n  esperado ${JSON.stringify(plano)}\n  obtenido ${JSON.stringify(obtenido)}`); }
}
console.log(`${casos.length - fallos} de ${casos.length} casos iguales a la base`);
process.exit(fallos ? 1 : 0);
