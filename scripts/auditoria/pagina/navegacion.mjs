// A2-15: al navegar, cada página nueva empieza arriba (en escritorio se desplaza el cuerpo de la página).
import puppeteer from "puppeteer-core";
const BASE = "http://127.0.0.1:8080";
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 850 });
await p.goto(BASE + "/", { waitUntil: "domcontentloaded" });
await p.evaluate(async (c) => fetch("/api/social/v1/sesiones", { method: "POST", headers: { "Content-Type": "application/json", "X-Parrhesia": "1" },
  body: JSON.stringify({ correo: "laura_castano@demo.parrhesia.local", clave: c }) }), process.env.CLAVE_DEMO);
await p.goto(BASE + "/", { waitUntil: "networkidle0" });
let fallos = 0;
const caso = (d, ok, det = "") => { if (!ok) fallos++; console.log(`${ok ? "OK   " : "FALLA"} A2-15 ${d}${ok ? "" : " → " + det}`); };
const desplazado = () => p.evaluate(() => Math.max(document.body.scrollTop, window.scrollY));
await p.mouse.move(700, 500);
for (let i = 0; i < 12; i++) { await p.mouse.wheel({ deltaY: 200 }); await new Promise((r) => setTimeout(r, 40)); }
await new Promise((r) => setTimeout(r, 500));
caso("el feed se desplaza", (await desplazado()) > 400, await desplazado());
// Abre una publicación que quedó visible abajo, haciendo clic en su hora.
const enlace = await p.evaluateHandle(() => [...document.querySelectorAll(".publicacion__hora")].find((a) => a.getBoundingClientRect().top > 100 && a.getBoundingClientRect().top < innerHeight));
await Promise.all([p.waitForNavigation({ waitUntil: "networkidle0" }), enlace.click()]);
caso("la publicación abierta empieza arriba", (await desplazado()) === 0, await desplazado());
await p.goBack({ waitUntil: "networkidle0" });
await p.click('a[href="/tendencias"]'); await new Promise((r) => setTimeout(r, 800));
caso("una sección del menú empieza arriba", (await desplazado()) === 0, await desplazado());
console.log("fallos:", fallos);
await b.close();
