// Uso: en una carpeta aparte, `npm install puppeteer-core@23.11.1` y `node recorrido_a.mjs` (Chrome instalado).
// Crea y al final desactiva una cuenta de prueba; interactúa con una publicación de laura_castano (demo).

// Bloque 4, recorrido A (FN-01 a FN-06): cuenta, publicar, doble clic, responder, compartir, reacciones.
// Usa la página como una persona y compara con la API. Imprime OK/FALLA y todos los errores que vio.
import puppeteer from "puppeteer-core";
const BASE = "http://127.0.0.1:8080";
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 900 });
const errores = [], respuestasMalas = [];
p.on("console", (m) => { if (m.type() === "error") errores.push(m.text().slice(0, 160)); });
p.on("pageerror", (e) => errores.push("pageerror: " + e.message.slice(0, 160)));
p.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 500) respuestasMalas.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, "")}`); });
let fallos = 0;
const caso = (id, d, ok, det = "") => { if (!ok) fallos++; console.log(`${ok ? "OK   " : "FALLA"} ${id} ${d}${ok ? "" : " → " + String(det).slice(0, 200)}`); };
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const api = (ruta, op = {}) => p.evaluate(async (ruta, op) => {
  const r = await fetch("/api" + ruta, { method: op.metodo || "GET", headers: { "Content-Type": "application/json", "X-Parrhesia": "1" }, body: op.cuerpo ? JSON.stringify(op.cuerpo) : undefined });
  let j = null; try { j = await r.json(); } catch {}
  return { status: r.status, json: j };
}, ruta, op);
const nombre = "fn_" + Date.now().toString(36);

// FN-01 · Crear cuenta desde el formulario
await p.goto(BASE + "/registro", { waitUntil: "networkidle0" });
const inputs = await p.$$("form.acceso__campos input");
await inputs[0].type("Prueba Funcional");
await inputs[1].type(nombre);
await inputs[2].type(nombre + "@auditoria.local");
await inputs[3].type("Clave-funcional-2026");
await Promise.all([p.waitForNavigation({ waitUntil: "networkidle0" }).catch(() => {}), p.click("form.acceso__campos button.boton--ancho")]);
const yo = await api("/social/v1/yo");
caso("FN-01", "crear cuenta desde el formulario deja la sesión iniciada", yo.status === 200 && yo.json.nombre_usuario === nombre, JSON.stringify(yo));

// FN-03 · Publicar una opinión desde el botón flotante
await p.goto(BASE + "/", { waitUntil: "networkidle0" });
await p.click(".publicar-flotante");
await p.waitForSelector(".compositor__texto");
await p.type(".compositor__texto", "Opinión de la prueba funcional #auditoriafn");
await p.click(".compositor .boton:not(.boton--borde)");
await espera(1500);
let mias = (await api(`/social/v1/usuarios/${nombre}/publicaciones`)).json.publicaciones;
caso("FN-03", "publicar una opinión crea exactamente una publicación", mias.length === 1, mias.length);
caso("FN-03", "el compositor se cierra al publicar", !(await p.$eval(".compositor", (d) => d.open).catch(() => false)));
caso("FN-03", "la etiqueta queda registrada", mias[0]?.etiquetas?.includes("auditoriafn"), JSON.stringify(mias[0]?.etiquetas));

// FN-03 · Doble clic en Publicar
await p.click(".publicar-flotante");
await p.waitForSelector(".compositor__texto");
await p.type(".compositor__texto", "Prueba de doble clic en publicar");
const boton = await p.$(".compositor .boton:not(.boton--borde)");
await Promise.all([boton.click(), boton.click(), boton.click()]);
await espera(2000);
mias = (await api(`/social/v1/usuarios/${nombre}/publicaciones`)).json.publicaciones;
caso("FN-03", "tres clics rápidos en Publicar crean una sola publicación", mias.filter((x) => x.texto?.includes("doble clic")).length === 1,
  mias.filter((x) => x.texto?.includes("doble clic")).length);

// FN-03 · Publicar con cifra: aparece como pendiente y luego con conclusión
await p.click(".publicar-flotante");
await p.waitForSelector(".compositor__texto");
await p.type(".compositor__texto", "La inflación anual de octubre de 2026 fue de 6,30 %.");
await p.click(".compositor .boton:not(.boton--borde)");
await espera(1500);
mias = (await api(`/social/v1/usuarios/${nombre}/publicaciones`)).json.publicaciones;
const cifra = mias.find((x) => x.texto?.includes("6,30"));
caso("FN-03", "publicar una cifra la guarda", !!cifra);
await p.goto(BASE + "/", { waitUntil: "networkidle0" });
const enInicio = await p.evaluate(() => document.body.innerText);
caso("FN-03", "lo publicado aparece en mi inicio", enInicio.includes("Opinión de la prueba funcional") && !enInicio.includes("Tu inicio está vacío"));

// FN-05 · Reacciones sobre una publicación real de la demo, abierta en su página
const deLaura = (await api("/social/v1/usuarios/laura_castano/publicaciones")).json.publicaciones.find((x) => !x.responde_a_id && !x.comparte_id && x.estado === "visible");
const idAjena = deLaura.id;
await p.goto(BASE + "/publicacion/" + idAjena, { waitUntil: "networkidle0" });
const ajena = await p.$("article.publicacion");
caso("FN-06", "en lo ajeno no aparece Retirar para una cuenta normal", !(await ajena.$(".publicacion__retirar")));
const antes = (await api(`/social/v1/publicaciones/${idAjena}`)).json?.totales;
const meGusta = await ajena.$("button[aria-label='Me gusta']");
for (let i = 0; i < 5; i++) await meGusta.click();
await espera(2500);
const despues = (await api(`/social/v1/publicaciones/${idAjena}`)).json?.totales;
const enPantalla = await ajena.$eval("button[aria-label='Me gusta'] .cifra", (e) => Number(e.innerText));
caso("FN-05", "cinco clics en Me gusta: queda marcado una vez (impar) y el contador sube 1", despues?.me_gusta === (antes?.me_gusta ?? 0) + 1,
  `antes ${JSON.stringify(antes)} después ${JSON.stringify(despues)} id ${idAjena}`);
caso("FN-05", "el número en pantalla coincide con la base", enPantalla === despues?.me_gusta, `${enPantalla} vs ${despues?.me_gusta}`);
await ajena.$("button[aria-label='Útil']").then((x) => x.click());
await espera(1500);
const trasUtil = (await api(`/social/v1/publicaciones/${idAjena}`)).json;
caso("FN-05", "cambiar a Útil reemplaza Me gusta (una reacción por persona)", trasUtil?.mi_reaccion === "util" && trasUtil?.totales.me_gusta === antes?.me_gusta,
  JSON.stringify(trasUtil?.totales));

// FN-04 · Compartir y deshacer, con clics repetidos
const compartir = await ajena.$("button[aria-label='Compartir'], button[aria-label='Deshacer compartida']");
await compartir.click(); await espera(1500);
let est = (await api(`/social/v1/publicaciones/${idAjena}`)).json;
caso("FN-04", "compartir: queda una compartida mía", !!est?.mi_compartida && est.totales.compartidas === (antes?.compartidas ?? 0) + 1, JSON.stringify(est?.totales));
await (await ajena.$("button[aria-label='Deshacer compartida']")).click(); await espera(1500);
est = (await api(`/social/v1/publicaciones/${idAjena}`)).json;
caso("FN-04", "deshacer: vuelve al número inicial", !est?.mi_compartida && est.totales.compartidas === (antes?.compartidas ?? 0), JSON.stringify(est?.totales));

// FN-04 · Responder desde la tarjeta y ver el hilo
await (await ajena.$("button[aria-label^='Responder']")).click();
await p.waitForSelector(".compositor__texto");
await p.type(".compositor__texto", "Respuesta de la prueba funcional.");
await p.click(".compositor .boton:not(.boton--borde)");
await espera(1500);
const hilo = (await api(`/social/v1/publicaciones/${idAjena}/hilo`)).json?.hilo || [];
caso("FN-04", "la respuesta aparece en el hilo de la publicación", hilo.some((h) => h.texto === "Respuesta de la prueba funcional."), hilo.length);
await p.goto(BASE + "/publicacion/" + idAjena, { waitUntil: "networkidle0" });
const textoPagina = await p.evaluate(() => document.body.innerText);
caso("FN-04", "la página del hilo muestra la respuesta", textoPagina.includes("Respuesta de la prueba funcional."));
const cuentaRespuestas = (await api(`/social/v1/publicaciones/${idAjena}`)).json?.totales.respuestas;
caso("FN-04", "el contador de respuestas coincide con el hilo", cuentaRespuestas === hilo.filter((h) => h.profundidad === 1).length,
  `${cuentaRespuestas} vs ${hilo.filter((h) => h.profundidad === 1).length}`);

// FN-06 · Retirar lo propio desde la página
await p.goto(BASE + "/", { waitUntil: "networkidle0" });
const mia = await p.evaluateHandle(() => [...document.querySelectorAll("article.publicacion")].find((a) => a.innerText.includes("Opinión de la prueba funcional")) || null);
const botonRetirar = (await mia.evaluate((e) => !!e)) ? await mia.$(".publicacion__retirar") : null;
caso("FN-06", "en lo propio aparece Retirar", !!botonRetirar);
if (botonRetirar) {
  await botonRetirar.click();
  await (await mia.$(".publicacion__si")).click();
  await espera(1500);
  const idOp = mias.find((x) => x.texto?.includes("Opinión de la prueba"))?.id;
  const estadoOp = (await api("/social/v1/publicaciones/" + idOp)).json?.estado;
  caso("FN-06", "tras confirmar, la publicación queda retirada en la base", estadoOp === "retirada_por_autor", estadoOp);
  caso("FN-06", "y la tarjeta lo muestra", (await mia.evaluate((e) => e.innerText)).includes("fue retirada"));
}

// FN-02 · Perfil propio coherente
await p.goto(BASE + "/perfil/" + nombre, { waitUntil: "networkidle0" });
const perfil = await api(`/social/v1/usuarios/${nombre}`);
const pubs = (await api(`/social/v1/usuarios/${nombre}/publicaciones`)).json.publicaciones;
caso("FN-02", "el perfil carga", perfil.status === 200);
caso("FN-02", "contador de publicaciones del perfil = publicaciones listadas", perfil.json?.estadisticas?.publicaciones === undefined || perfil.json.estadisticas.publicaciones >= pubs.length,
  JSON.stringify(perfil.json?.estadisticas));

// Limpieza: desactivar la cuenta de prueba
await api("/social/v1/yo/desactivacion", { metodo: "POST", cuerpo: { clave_actual: "Clave-funcional-2026" } });
console.log("\nCuenta de prueba:", nombre);
console.log("Errores de consola:", errores.length ? errores : "ninguno");
console.log("Respuestas 5xx de la API:", respuestasMalas.length ? respuestasMalas : "ninguna");
console.log("Casos fallidos:", fallos);
await b.close();
