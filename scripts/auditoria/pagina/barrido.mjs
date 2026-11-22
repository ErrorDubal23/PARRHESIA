// Bloque 4, barrido: todas las rutas, con y sin sesión, escritorio y celular, claro y oscuro.
// Por ruta: errores de consola, respuestas 5xx, textos rotos y desborde horizontal.
import puppeteer from "puppeteer-core";
const BASE = "http://127.0.0.1:8080";
const ID = JSON.parse(process.env.IDS);
const RUTAS = ["/", "/temas", `/temas/${ID.tema}`, "/tendencias", `/tendencias/${ID.etiqueta}`, "/comunidades",
  `/comunidades/${ID.comunidad_publica}`, `/comunidades/${ID.comunidad_privada}`, "/figuras", `/figuras/${ID.figura}`,
  "/datos", `/datos/${ID.serie}`, `/datos/dato/${ID.dato}`, "/analizar", `/analizar/${ID.enlace}`,
  `/publicacion/${ID.pub}`, "/perfil/laura_castano", "/equipo", "/buscar?q=laura", "/revisiones",
  "/publicacion/00000000-0000-0000-0000-000000000000", "/perfil/no_existe_nadie", "/ruta/que/no/existe"];
const CONFIGS = [
  { nombre: "escritorio-claro-sesion", ancho: 1440, alto: 900, tema: "claro", sesion: true },
  { nombre: "celular-oscuro-sesion", ancho: 390, alto: 844, tema: "oscuro", sesion: true },
  { nombre: "escritorio-oscuro-anonimo", ancho: 1280, alto: 800, tema: "oscuro", sesion: false },
];
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
let total = 0;
for (const c of CONFIGS) {
  const ctx = await b.createBrowserContext();
  const p = await ctx.newPage();
  await p.setViewport({ width: c.ancho, height: c.alto, isMobile: c.ancho < 500, hasTouch: c.ancho < 500 });
  let errores = [], malas = [];
  p.on("console", (m) => { if (m.type() === "error" && !/401|status of 404/.test(m.text())) errores.push(m.text().slice(0, 140)); });
  p.on("pageerror", (e) => errores.push("pageerror: " + e.message.slice(0, 140)));
  p.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 500) malas.push(r.status() + " " + r.url().replace(BASE, "")); });
  await p.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  await p.evaluate((t) => { try { localStorage.setItem("parrhesia.tema", t); } catch {} }, c.tema);
  if (c.sesion) await p.evaluate(async (clave) => fetch("/api/social/v1/sesiones", { method: "POST", headers: { "Content-Type": "application/json", "X-Parrhesia": "1" },
    body: JSON.stringify({ correo: "laura_castano@demo.parrhesia.local", clave }) }), process.env.CLAVE_DEMO);
  console.log(`\n== ${c.nombre}`);
  for (const ruta of RUTAS) {
    errores = []; malas = [];
    await p.goto(BASE + ruta, { waitUntil: "networkidle0", timeout: 30000 }).catch(() => {});
    await p.evaluate((t) => document.documentElement.setAttribute("data-tema", t), c.tema);
    await new Promise((r) => setTimeout(r, 700));
    const info = await p.evaluate(() => {
      const texto = document.querySelector(".principal")?.innerText ?? document.body.innerText;
      const rotos = (texto.match(/\bundefined\b|\bNaN\b|\[object Object\]|\bnull\b|Invalid Date/g) || []);
      const anchoDoc = document.documentElement.scrollWidth, anchoVentana = window.innerWidth;
      const culpables = anchoDoc > anchoVentana + 1 ? [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > anchoVentana + 1 && getComputedStyle(e).position !== "fixed")
        .slice(0, 3).map((e) => e.tagName.toLowerCase() + "." + [...e.classList].join(".")) : [];
      return { rotos: [...new Set(rotos)], desborde: anchoDoc - anchoVentana, culpables, vacio: texto.trim().length < 20, titulo: document.querySelector("h1")?.innerText?.slice(0, 50) };
    });
    const problemas = [];
    if (errores.length) problemas.push("consola: " + errores.slice(0, 2).join(" | "));
    if (malas.length) problemas.push("5xx: " + malas.slice(0, 2).join(" | "));
    if (info.rotos.length) problemas.push("texto roto: " + info.rotos.join(","));
    if (info.desborde > 1) problemas.push(`desborde ${info.desborde}px: ${info.culpables.join(" ")}`);
    if (info.vacio) problemas.push("página casi vacía");
    total += problemas.length ? 1 : 0;
    console.log(`${problemas.length ? "FALLA" : "OK   "} ${ruta}  [${info.titulo ?? "-"}]${problemas.length ? "\n        " + problemas.join("\n        ") : ""}`);
  }
  await ctx.close();
}
console.log(`\nRutas con problemas: ${total}`);
await b.close();
