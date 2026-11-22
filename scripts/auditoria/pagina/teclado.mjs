// FN-18: uso solo con teclado.
import puppeteer from "puppeteer-core";
const BASE = "http://127.0.0.1:8080";
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
await p.goto(BASE + "/", { waitUntil: "domcontentloaded" });
await p.evaluate(async (clave) => fetch("/api/social/v1/sesiones", { method: "POST", headers: { "Content-Type": "application/json", "X-Parrhesia": "1" }, body: JSON.stringify({ correo: "laura_castano@demo.parrhesia.local", clave }) }), process.env.CLAVE_DEMO);
await p.goto(BASE + "/", { waitUntil: "networkidle0" });
let fallos = 0;
const caso = (d, ok, det = "") => { if (!ok) fallos++; console.log(`${ok ? "OK   " : "FALLA"} FN-18 ${d}${ok ? "" : " → " + det}`); };
const vistos = [], sinFoco = [];
for (let i = 0; i < 40; i++) {
  await p.keyboard.press("Tab");
  const f = await p.evaluate(() => {
    const e = document.activeElement; if (!e || e === document.body) return null;
    const marca = (x) => { const s = getComputedStyle(x); return (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || (s.boxShadow && s.boxShadow !== "none"); };
    const visible = marca(e) || (e.closest(".buscador") ? marca(e.closest(".buscador")) : false);
    return { que: (e.getAttribute("aria-label") || e.innerText || e.placeholder || e.tagName).trim().slice(0, 30), visible };
  });
  if (!f) continue;
  vistos.push(f.que);
  if (!f.visible) sinFoco.push(f.que);
}
caso("Tab llega al menú, al buscador y a las acciones de las tarjetas",
  vistos.some((v) => /Inicio|Temas/.test(v)) && vistos.some((v) => /Buscar/i.test(v)) && vistos.some((v) => /Me gusta|Responder|Compartir/.test(v)), vistos.slice(0, 12).join(" · "));
caso("todo lo que recibe el foco lo muestra", sinFoco.length === 0, [...new Set(sinFoco)].slice(0, 6).join(" · "));
await p.evaluate(() => document.activeElement?.blur());
await p.keyboard.press("n");
await new Promise((r) => setTimeout(r, 500));
caso("la tecla N abre el compositor", await p.$eval(".compositor", (d) => d.open).catch(() => false));
await p.keyboard.press("Escape");
await new Promise((r) => setTimeout(r, 400));
caso("Escape lo cierra", !(await p.$eval(".compositor", (d) => d.open).catch(() => false)));
const tarjeta = await p.$("article.publicacion");
await tarjeta.focus().catch(() => {});
const enfocable = await tarjeta.evaluate((a) => a.tabIndex >= 0 || !!a.querySelector("a[href^='/publicacion/']"));
caso("cada tarjeta se puede abrir con el teclado (es enfocable o tiene un enlace)", enfocable);
await b.close();
console.log("fallos:", fallos);
