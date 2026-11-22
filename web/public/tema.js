// Tema antes de pintar, para que no parpadee (archivo aparte: la política de seguridad no permite scripts en línea).
try {
  var t = localStorage.getItem("tema");
  if (!t) t = matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
  document.documentElement.dataset.tema = t;
} catch (e) {
  document.documentElement.dataset.tema = "claro";
}
