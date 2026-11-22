// Ejemplos para la presentación (modo demostración, VITE_MODO_DEMO=1). Solo llenan el campo de texto: la persona
// revisa, cambia lo que quiera y decide si publica. Nada se publica solo.
//
// Las cifras de las publicaciones están escritas como las diría cualquiera en una red: unas coinciden con el dato
// oficial cargado y otras no (otro periodo, otra dirección, otra ciudad, otro indicador). El ejemplo no dice cuál es
// cuál: eso lo decide la verificación con la base y sus reglas, igual que con cualquier publicación.
// Datos oficiales cargados al preparar estos ejemplos (22 nov 2026): inflación anual hasta octubre de 2026,
// desempleo nacional hasta septiembre de 2026 y homicidios nacionales hasta septiembre de 2026.
// Los enlaces son noticias reales de esos días; los textos para pegar imitan mensajes que circulan sin fuente.

export type TipoEjemplo = "cifra" | "opinion";
export interface Ejemplo { texto: string; tipo: TipoEjemplo }

export const PUBLICACIONES: Ejemplo[] = [
  { tipo: "cifra", texto: "La inflación anual de octubre de 2026 fue de 6,30 %, casi igual que en septiembre. #inflacion" },
  { tipo: "cifra", texto: "Por fin una buena noticia: la inflación bajó en octubre de 2026 y quedó en 6,1 %. #inflacion" },
  { tipo: "cifra", texto: "En septiembre de 2026 el desempleo quedó en 8 %, por debajo del 8,2 % de un año antes. #desempleo" },
  { tipo: "cifra", texto: "El desempleo subió en septiembre de 2026 frente a agosto. Cada mes hay menos trabajo. #desempleo" },
  { tipo: "cifra", texto: "En septiembre de 2026 hubo 966 homicidios en el país, la cifra mensual más baja del año. #seguridad" },
  { tipo: "cifra", texto: "Los homicidios aumentaron en septiembre de 2026 frente a agosto. La seguridad va para atrás. #seguridad" },
  { tipo: "cifra", texto: "En enero de 2026 el desempleo pasó del 10 %. ¿Efecto de temporada o algo más? #desempleo" },
  { tipo: "cifra", texto: "La inflación anual cerró 2025 en 5,1 % y ya va en 6,3 % en octubre de 2026. #inflacion #salariominimo" },
  { tipo: "cifra", texto: "En Cali el desempleo está en 15 %, el doble que en el resto del país. #desempleo" },
  { tipo: "cifra", texto: "La pobreza monetaria bajó a 30 % este año, según dicen en el Congreso. #pobreza" },
  { tipo: "opinion", texto: "Creo que la discusión del salario mínimo debería empezar por la productividad y no solo por el porcentaje. #salariominimo" },
  { tipo: "opinion", texto: "Me preocupa que se hable de seguridad solo con promedios nacionales; en los barrios se vive distinto. #seguridad" },
  { tipo: "opinion", texto: "El metro va a cambiar la ciudad, pero las obras están siendo muy duras para el comercio del sector. #movilidadbogota" },
  { tipo: "opinion", texto: "Ojalá todos los debates económicos citaran la fuente. Así se discute mejor, se piense lo que se piense. #datosabiertos" },
  { tipo: "opinion", texto: "No comparto la política de seguridad actual, pero reconozco que hay que esperar más meses para evaluarla. #seguridad" },
];

export const RESPUESTAS: Ejemplo[] = [
  { tipo: "opinion", texto: "¿De dónde sale esa cifra? Me gustaría ver la fuente." },
  { tipo: "opinion", texto: "Revisé la ficha del dato y el periodo no es el mismo que dices." },
  { tipo: "opinion", texto: "Buen punto, aunque lo veo distinto: el promedio esconde diferencias grandes entre regiones." },
  { tipo: "opinion", texto: "No estoy de acuerdo, pero gracias por explicar tu postura con argumentos." },
  { tipo: "opinion", texto: "Separemos lo que es dato de lo que es interpretación; en lo segundo podemos pensar distinto." },
  { tipo: "cifra", texto: "La inflación anual de septiembre de 2026 fue de 6,29 %, así que octubre casi no cambió." },
  { tipo: "cifra", texto: "El desempleo de agosto de 2026 fue de 9,4 %; en septiembre bajó bastante." },
  { tipo: "cifra", texto: "En agosto de 2026 hubo 1.190 homicidios, así que septiembre sí fue más bajo." },
];

/** Noticias reales con cifras de los indicadores cargados (revisadas el 22 nov 2026: la página se deja leer). */
export const ENLACES: { url: string; medio: string; tema: string }[] = [
  { medio: "Valora Analitik", tema: "Inflación de octubre de 2026",
    url: "https://www.valoraanalitik.com/inflacion-colombia-octubre-2026-escalo-leve/" },
  { medio: "Semana", tema: "Inflación de octubre de 2026",
    url: "https://www.semana.com/economia/macroeconomia/articulo/nueva-subida-de-la-inflacion-en-colombia-en-octubre-de-2026-fue-de-630/202618/" },
  { medio: "La República", tema: "Inflación de octubre de 2026",
    url: "https://amp.larepublica.co/economia/el-dane-revelo-que-la-inflacion-en-el-decimo-mes-del-ano-llego-hasta-6-30-4520889" },
  { medio: "Pyme Noticias", tema: "Desempleo de septiembre de 2026",
    url: "https://www.pymenoticias.com/post/desempleo-septiembre-dane-sectores-ciudades-pymes" },
  { medio: "El Heraldo", tema: "Homicidios en agosto de 2026",
    url: "https://www.elheraldo.co/colombia/2026/09/26/homicidios-bajaron-6-en-el-primer-mes-del-gobierno-de-abelardo-de-la-espriella/" },
  { medio: "La Silla Vacía", tema: "Seguridad en los primeros 100 días",
    url: "https://www.lasillavacia.com/silla-nacional/cifras-de-seguridad-mejoran-tras-100-dias-del-gobierno-de-la-espriella/" },
  { medio: "Infobae", tema: "Inflación de alimentos en octubre de 2026",
    url: "https://www.infobae.com/colombia/2026/11/13/el-precio-de-los-alimentos-en-colombia-en-octubre-de-2026-llego-al-nivel-mas-alto-desde-2023-hay-preocupacion-por-la-inflacion-del-pais/" },
];

/** Mensajes para pegar en "Texto": imitan cadenas que circulan sin fuente. No se atribuyen a nadie. */
export const TEXTOS: string[] = [
  "Mensaje reenviado muchas veces: «La inflación en Colombia bajó en octubre de 2026 y quedó en 5,9 %. ¡Compartan!»",
  "Cadena de WhatsApp: el desempleo de agosto de 2026 llegó a 9,4 %, el más alto de todo el año. Nadie lo dice en las noticias.",
  "Circula en redes: en septiembre de 2026 hubo 966 homicidios en Colombia, casi 20 % menos que en agosto.",
  "Imagen viral: «Con este gobierno la inflación anual ya pasó del 7 % en octubre de 2026».",
];

/** Un elemento al azar distinto del anterior, para que dos clics seguidos no repitan. */
export function alAzar<T>(lista: T[], anterior?: T): T {
  if (lista.length < 2) return lista[0];
  let elegido = anterior;
  while (elegido === anterior) elegido = lista[Math.floor(Math.random() * lista.length)];
  return elegido as T;
}

export const MODO_DEMO = import.meta.env.VITE_MODO_DEMO === "1";
