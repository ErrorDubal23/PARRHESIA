// Cliente de la API: todo pasa por la puerta de entrada (/api/<servicio>/v1/...).
// Los errores llegan siempre con la misma forma: {"error": {"codigo", "mensaje"}}.

export class ErrorApi extends Error {
  constructor(public codigo: string, mensaje: string, public estado: number) {
    super(mensaje);
  }
}

// La sesión vive en una cookie HttpOnly que pone el servidor: este código nunca ve ni guarda
// el token. Cada petición lleva X-Parrhesia, que el servidor exige en las escrituras (anti-CSRF).

export async function api<T>(ruta: string, opciones: { metodo?: string; cuerpo?: unknown } = {}): Promise<T> {
  const archivo = opciones.cuerpo instanceof FormData; // subida de archivos: el navegador pone su propio tipo
  const respuesta = await fetch(`/api${ruta}`, {
    method: opciones.metodo ?? "GET",
    credentials: "same-origin",
    headers: {
      "X-Parrhesia": "1",
      ...(opciones.cuerpo !== undefined && !archivo ? { "Content-Type": "application/json" } : {}),
    },
    body: archivo ? (opciones.cuerpo as FormData) : opciones.cuerpo !== undefined ? JSON.stringify(opciones.cuerpo) : undefined,
  });
  if (respuesta.status === 204) return undefined as T;
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const error = datos?.error ?? { codigo: "error", mensaje: "Algo no salió bien. Intenta de nuevo." };
    if (respuesta.status === 401 && ruta !== "/social/v1/sesiones") window.dispatchEvent(new Event("sesion-vencida"));
    throw new ErrorApi(error.codigo, error.mensaje, respuesta.status);
  }
  return datos as T;
}

/** Solo rutas internas como destino después de entrar (evita redirecciones a sitios ajenos). */
export function destinoSeguro(valor: string | null): string {
  return valor && valor.startsWith("/") && !valor.startsWith("//") && !valor.startsWith("/\\") ? valor : "/";
}

// --- Formato -----------------------------------------------------------------------------------

/** Cifra en formato colombiano. Las cifras llegan como texto (decisión 24): nunca se pasan por float
 *  para guardar; aquí solo se redondean para mostrarse (decisión 27). El valor exacto va en el title. */
export function cifra(valor: string | null | undefined, maxDecimales = 2): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const [entero, decimal = ""] = valor.split(".");
  let dec = decimal.replace(/0+$/, "");
  let ent = entero;
  if (dec.length > maxDecimales) {
    const redondeado = Number(`${entero}.${decimal}`).toFixed(maxDecimales);
    [ent, dec] = redondeado.split(".");
    dec = (dec ?? "").replace(/0+$/, "");
  }
  const negativo = ent.startsWith("-");
  const digitos = negativo ? ent.slice(1) : ent;
  const miles = digitos.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${negativo ? "−" : ""}${miles}${dec ? "," + dec : ""}`;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

export function periodo(p: string | null | undefined, corto = false): string {
  if (!p) return "—";
  if (p.length === 4) return p;
  const mes = Number(p.slice(5, 7)) - 1;
  return corto ? `${MESES_CORTOS[mes]} ${p.slice(2, 4)}` : `${MESES[mes]} de ${p.slice(0, 4)}`;
}

export function haceCuanto(fecha: string): string {
  const s = Math.max(1, (Date.now() - new Date(fecha).getTime()) / 1000);
  if (s < 60) return "ahora";
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d`;
  return new Date(fecha).toLocaleDateString("es-CO", { day: "numeric", month: "short" });
}

// Espacio fino antes del %, como en la norma colombiana: "9,4 %".
export const UNIDAD: Record<string, string> = { inflation: "\u202f%", unemployment: "\u202f%", public_debt: "\u202f%" };
export const INDICADOR: Record<string, string> = {
  inflation: "Inflación", unemployment: "Desempleo", minimum_wage: "Salario mínimo", public_debt: "Deuda pública",
  homicides: "Homicidios", theft: "Hurtos", extortion: "Extorsión", kidnapping: "Secuestro",
};

/** Nombre legible de los canales de acceso (el catálogo guarda su código). */
export const CANAL: Record<string, string> = {
  dane_web: "web del DANE",
  banrep_suameca: "SUAMECA del Banco de la República",
  mindefensa_datos_gov_co: "datos.gov.co (MinDefensa)",
};
export const nombreCanal = (codigo: string) => CANAL[codigo] ?? codigo;
