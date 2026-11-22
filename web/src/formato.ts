// Formato de las publicaciones: **negrita**, *cursiva* y [texto](https://enlace). Nunca HTML.
// Las reglas son las mismas de util.texto_plano (migración 0016): lo que aquí se cuenta como
// visible es exactamente lo que la base cuenta para el límite de 500 caracteres.

export const MAXIMO_VISIBLE = 500;
export const MAXIMO_CON_MARCAS = 1500;

// Una marca no empieza ni termina con espacio y no va pegada a letras o números por fuera:
// así "5 * 3" o "2*4*5" no se toman como cursiva (las cifras nunca se juntan por el formato).
const ENLACE = /\[([^\]\n]{1,200})\]\((https:\/\/[^\s)]+)\)/g;
const NEGRITA = /(^|[^\p{L}\p{N}*])\*\*([^*\s]|[^*\s][^*\n]*[^*\s])\*\*(?![\p{L}\p{N}*])/gu;
const CURSIVA = /(^|[^\p{L}\p{N}*])\*([^*\s]|[^*\s][^*\n]*[^*\s])\*(?![\p{L}\p{N}*])/gu;

/** El texto como se lee, sin marcas (igual que util.texto_plano en la base). */
export function textoPlano(texto: string): string {
  return texto.replace(ENLACE, "$1").replace(NEGRITA, "$1$2").replace(CURSIVA, "$1$2");
}

export type Nodo =
  | { tipo: "texto"; valor: string }
  | { tipo: "negrita"; hijos: Nodo[] }
  | { tipo: "cursiva"; hijos: Nodo[] }
  | { tipo: "enlace"; etiqueta: string; url: string; dominio: string };

/** Solo enlaces https bien formados; el dominio se muestra siempre junto al texto del enlace. */
export function dominioSeguro(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && !u.username && !u.password ? u.hostname.replace(/^www\./, "") : null;
  } catch {
    return null;
  }
}

function porPatron(texto: string, patron: RegExp, crear: (m: RegExpMatchArray) => Nodo[], resto: (s: string) => Nodo[]): Nodo[] {
  const nodos: Nodo[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(patron)) {
    nodos.push(...resto(texto.slice(ultimo, m.index)));
    nodos.push(...crear(m));
    ultimo = (m.index ?? 0) + m[0].length;
  }
  nodos.push(...resto(texto.slice(ultimo)));
  return nodos.filter((n) => n.tipo !== "texto" || n.valor !== "");
}

const soloTexto = (s: string): Nodo[] => [{ tipo: "texto", valor: s }];
const cursivas = (s: string) =>
  porPatron(s, CURSIVA, (m) => [...soloTexto(m[1]), { tipo: "cursiva", hijos: soloTexto(m[2]) }], soloTexto);
const negritas = (s: string) =>
  porPatron(s, NEGRITA, (m) => [...soloTexto(m[1]), { tipo: "negrita", hijos: cursivas(m[2]) }], cursivas);

/** El texto con formato como árbol de nodos (la app lo dibuja con elementos, nunca con HTML). */
export function analizar(texto: string): Nodo[] {
  return porPatron(texto, ENLACE, (m) => {
    const dominio = dominioSeguro(m[2]);
    return dominio ? [{ tipo: "enlace", etiqueta: textoPlano(m[1]), url: m[2], dominio }] : soloTexto(m[0]);
  }, negritas);
}
