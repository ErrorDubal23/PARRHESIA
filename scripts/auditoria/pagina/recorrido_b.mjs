// Bloque 4, recorrido B (FN-07 a FN-16 y FN-20) con una cuenta de la demo (laura_castano).
import puppeteer from "puppeteer-core";
const BASE = "http://127.0.0.1:8080";
const ID = JSON.parse(process.env.IDS);
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
const errores = [], malas = [];
p.on("console", (m) => { if (m.type() === "error" && !/401|status of 404|status of 4/.test(m.text())) errores.push(m.text().slice(0, 140)); });
p.on("pageerror", (e) => errores.push("pageerror: " + e.message.slice(0, 140)));
p.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 500) malas.push(r.status() + " " + r.url().replace(BASE, "")); });
let fallos = 0;
const caso = (id, d, ok, det = "") => { if (!ok) fallos++; console.log(`${ok ? "OK   " : "FALLA"} ${id} ${d}${ok ? "" : " → " + String(det).slice(0, 220)}`); };
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const ir = (ruta) => p.goto(BASE + ruta, { waitUntil: "networkidle0" });
const texto = () => p.evaluate(() => document.querySelector(".principal")?.innerText ?? document.body.innerText);
const api = (ruta, op = {}) => p.evaluate(async (ruta, op) => {
  const r = await fetch("/api" + ruta, { method: op.metodo || "GET", headers: { "Content-Type": "application/json", "X-Parrhesia": "1" }, body: op.cuerpo ? JSON.stringify(op.cuerpo) : undefined });
  let j = null; try { j = await r.json(); } catch {}
  return { status: r.status, json: j };
}, ruta, op);
await ir("/");
await api("/social/v1/sesiones", { metodo: "POST", cuerpo: { correo: "laura_castano@demo.parrhesia.local", clave: process.env.CLAVE_DEMO } });

// FN-07 · Verificación: abrir el análisis de una publicación con conclusión
await ir("/publicacion/" + ID.pub);
const verificado = await api("/verificacion/v1/textos/publicacion/" + ID.pub);
const conclusion = verificado.json?.afirmaciones?.find((a) => a.verificacion)?.verificacion?.conclusion;
const boton = await p.$(".publicacion__veredicto");
caso("FN-07", "la publicación verificada muestra su conclusión", !!boton && !!conclusion, conclusion);
if (boton) { await boton.click(); await espera(1200); }
const t7 = await texto();
const nombre = { se_sostiene: "sostiene", se_debilita: "debilita", se_invierte: "invierte", sin_dato_comparable: "sin dato" }[conclusion];
caso("FN-07", "el análisis dice la misma conclusión que la base", t7.toLowerCase().includes(nombre ?? "???"), conclusion);
caso("FN-07", "el análisis muestra la fuente oficial", /DANE|Banco de la República|Policía|SUAMECA|fuente/i.test(t7));
caso("FN-07", "el análisis enseña a comprobarlo", /Compruébalo|consult/i.test(t7));
caso("FN-07", "no dice verdadero ni falso", !/\bverdadero\b|\bfalso\b|\bmentira\b/i.test(t7));
await ir("/figuras/" + ID.figura);
const t7b = await texto();
caso("FN-07", "la ficha de la figura lista sus declaraciones con su fuente", (t7b.match(/«/g) || []).length >= 2 && /Fuente|fuente/.test(t7b));

// FN-08 · Analizar: texto pegado y red social cerrada
await ir("/analizar");
await (await p.$$(".pestanas button"))[1].click();
await p.type(".analizar__formulario textarea", "Circula en redes que el desempleo de septiembre de 2026 fue de 8 % en Colombia.");
await Promise.all([p.waitForNavigation({ waitUntil: "networkidle0", timeout: 20000 }).catch(() => {}), p.click(".analizar__acciones button:last-child")]);
await p.waitForSelector(".analizar__subtitulo", { timeout: 15000 }).catch(() => {});
caso("FN-08", "analizar un texto lleva a su análisis", /\/analizar\/[0-9a-f-]{36}/.test(p.url()), p.url());
caso("FN-08", "el análisis lista lo que se dijo con cifras", (await texto()).includes("Lo que se dijo con cifras"));
await ir("/analizar");
await p.type(".analizar__formulario input", "https://x.com/alguien/status/123456");
await p.click(".analizar__acciones button:last-child");
await espera(2500);
const t8 = await texto();
caso("FN-08", "un enlace de red social pide pegar el texto, con mensaje claro", /texto|pega/i.test(t8) && !!(await p.$(".aviso")), t8.slice(0, 200));

// FN-09 · Temas del día
await ir("/temas");
const recortes = await p.$$(".recorte");
caso("FN-09", "la página de temas muestra temas", recortes.length > 0, recortes.length);
if (recortes.length) {
  await Promise.all([p.waitForNavigation({ waitUntil: "networkidle0" }), p.click(".recorte__seguir")]);
  caso("FN-09", "'Leer el tema completo' abre el tema", /\/temas\/[0-9a-f-]{36}/.test(p.url()));
  await p.waitForSelector(".pestanas", { timeout: 15000 }).catch(() => {});
  const tabs = await p.$$(".pestanas button");
  if (tabs[1] && !(await tabs[1].evaluate((x) => x.getAttribute("aria-selected") === "true"))) { await tabs[1].click(); }
  await espera(600);
  const articulos = await p.$$eval("a.articulo", (as) => as.map((a) => a.href));
  caso("FN-09", "el tema lista sus artículos con enlace al medio", articulos.length > 0 && articulos.every((h) => h.startsWith("http")), articulos.length);
}

// FN-10 · Tendencias: clic en una barra
await ir("/tendencias");
const barras = await p.$$(".barra-tendencia");
const hayTendencias = (await api("/social/v1/tendencias")).json.tendencias.length > 0;
// Sin publicaciones en las últimas 24 horas no hay tendencias: la página debe decirlo (la demo se resiembra el día de la presentación).
caso("FN-10", hayTendencias ? "la gráfica tiene barras" : "sin tendencias, la página lo explica", hayTendencias ? barras.length > 0 : /Aún no hay tendencias/.test(await texto()), barras.length);
if (barras.length) {
  await Promise.all([p.waitForNavigation({ waitUntil: "networkidle0" }), barras[0].click()]);
  caso("FN-10", "clic en una barra abre su tendencia", /\/tendencias\/[^/]+$/.test(p.url()), p.url());
}
const tend = (await api("/social/v1/tendencias")).json;
caso("FN-10", "las barras coinciden con las tendencias de la base", barras.length === tend.tendencias.length, `${barras.length} vs ${tend.tendencias.length}`);

// FN-11 · Comunidades: validación del formulario (sin crear) y unirse/salir de una pública
await ir("/comunidades");
await p.click(".cabecera-seccion .boton");
await espera(500);
const campos = await p.$$("dialog[open] input, dialog[open] textarea");
if (campos.length >= 2) {
  await campos[0].type("ab"); await campos[1].type("corta");
  await p.$eval("dialog[open] form", (f) => f.requestSubmit());
  await espera(800);
  const valido = await p.$eval("dialog[open] form", (f) => f.checkValidity()).catch(() => null);
  caso("FN-11", "el formulario de comunidad no envía datos inválidos (nombre de 2 letras)", valido === false, valido);
  const antes = (await api("/social/v1/comunidades?q=ab")).json?.comunidades?.filter((c) => c.nombre === "ab").length;
  caso("FN-11", "no se creó ninguna comunidad inválida", antes === 0, antes);
} else caso("FN-11", "se abre el formulario de crear comunidad", false, campos.length);
await p.keyboard.press("Escape");
const publica = (await api("/social/v1/comunidades")).json.comunidades.find((c) => c.privacidad === "publica" && !c.mi_papel);
if (publica) {
  await ir("/comunidades/" + publica.id);
  const unirme = await p.$$eval("button.boton", (bs) => bs.findIndex((x) => x.innerText.includes("Unirme")));
  if (unirme >= 0) { await (await p.$$("button.boton"))[unirme].click(); await espera(1200); }
  let c = (await api("/social/v1/comunidades/" + publica.id)).json;
  caso("FN-11", "unirse a una comunidad pública", c?.mi_papel === "integrante", c?.mi_papel);
  const salir = await p.$$eval("button.boton-texto", (bs) => bs.findIndex((x) => x.innerText.trim() === "Salir"));
  if (salir >= 0) { await (await p.$$("button.boton-texto"))[salir].click(); await espera(1200); }
  c = (await api("/social/v1/comunidades/" + publica.id)).json;
  caso("FN-11", "salir de la comunidad", !c?.mi_papel, c?.mi_papel);
  caso("FN-11", "el contador de integrantes vuelve a su número", c?.total_integrantes === publica.total_integrantes, `${c?.total_integrantes} vs ${publica.total_integrantes}`);
} else caso("FN-11", "hay una comunidad pública a la que unirse", false);

// FN-12 · Figuras: el formulario de propuesta exige fuente https
await ir("/figuras");
await p.click(".cabecera-seccion .boton");
await espera(500);
const enDialogo = await p.$$("dialog[open] input");
caso("FN-12", "se abre 'Proponer una figura'", enDialogo.length >= 3, enDialogo.length);
if (enDialogo.length >= 3) {
  await enDialogo[0].type("Persona De Prueba Auditoria"); await enDialogo[1].type("Concejal"); await enDialogo[2].type("http://sin-https.example");
  await p.$eval("dialog[open] form", (f) => f.requestSubmit());
  await espera(1500);
  const avisoProp = await p.$eval("dialog[open] [role=alert], dialog[open] .aviso", (e) => e.innerText).catch(() => "");
  caso("FN-12", "una fuente mal escrita se rechaza con un mensaje en el formulario", avisoProp.length > 0, "sin mensaje");
  const creadas = (await api("/social/v1/figuras")).json.figuras.filter((f) => f.nombre_completo.includes("Auditoria")).length;
  caso("FN-12", "y no se crea nada", creadas === 0, creadas);
}
await p.keyboard.press("Escape");

// FN-15 · Búsqueda
await ir("/");
await p.type(".buscador input", "#ciudades"); await p.keyboard.press("Enter");
await espera(1500);
caso("FN-15", "buscar #etiqueta lleva a su tendencia", p.url().endsWith("/tendencias/ciudades"), p.url());
await p.type(".buscador input", "laura"); await p.keyboard.press("Enter");
await espera(1500);
caso("FN-15", "buscar 'laura' encuentra a Laura Castaño", (await texto()).includes("Laura Castaño"));
await p.type(".buscador input", "'; DROP TABLE x; --"); await p.keyboard.press("Enter");
await espera(1500);
caso("FN-15", "una búsqueda con caracteres raros responde sin romperse", (await texto()).length > 0 && !malas.some((m) => m.includes("usuarios")));

// FN-20 · Coherencia: cada tarjeta del inicio contra la base
await ir("/");
const tarjetas = await p.$$eval("article.publicacion", (as) => as.slice(0, 15).map((a) => ({
  href: a.querySelector("a[href^='/publicacion/']")?.getAttribute("href"),
  respuestas: Number(a.querySelector("button[aria-label^='Responder'] .cifra")?.innerText),
  compartidas: Number(a.querySelectorAll(".publicacion__acciones .accion")[1]?.querySelector(".cifra")?.innerText),
  meGusta: Number(a.querySelector("button[aria-label='Me gusta'] .cifra")?.innerText),
})));
let distintas = [];
for (const t of tarjetas) {
  const id = t.href?.split("/").pop();
  if (!id) continue;
  const tot = (await api("/social/v1/publicaciones/" + id)).json?.totales;
  if (tot && (tot.respuestas !== t.respuestas || tot.compartidas !== t.compartidas || tot.me_gusta !== t.meGusta)) distintas.push(`${id.slice(0, 8)} pantalla ${t.respuestas}/${t.compartidas}/${t.meGusta} base ${tot.respuestas}/${tot.compartidas}/${tot.me_gusta}`);
}
caso("FN-20", `los conteos de ${tarjetas.length} tarjetas del inicio coinciden con la base`, distintas.length === 0, distintas.join(" | "));

// FN-16 · Navegación: atrás/adelante, recargar en una ruta profunda, cerrar sesión
await ir("/figuras/" + ID.figura); await ir("/datos/" + ID.serie);
await p.goBack({ waitUntil: "networkidle0" });
caso("FN-16", "atrás vuelve a la página anterior", p.url().includes("/figuras/"), p.url());
await p.reload({ waitUntil: "networkidle0" });
caso("FN-16", "recargar una ruta profunda la vuelve a mostrar", (await texto()).includes("Leonardo Villar"));
await api("/social/v1/sesiones/actual", { metodo: "DELETE" });
await ir("/revisiones");
caso("FN-16", "sin sesión, una página del equipo pide iniciar sesión", /inicia sesión|entrar/i.test(await texto()));

console.log("\nErrores de consola:", errores.length ? [...new Set(errores)] : "ninguno");
console.log("Respuestas 5xx de la API:", malas.length ? malas : "ninguna");
console.log("Casos fallidos:", fallos);
await b.close();
