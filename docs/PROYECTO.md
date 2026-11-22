# Plataforma de Auditoría Informativa Neutral — Investigación y propuestas

## Brief del proyecto: fuente única de verdad (redefinido el 20 nov 2026)

Esta sección manda sobre todo lo demás del documento. Las secciones de más abajo sobre despolarización son contexto histórico y **no** son objetivos del proyecto.

**Redefinición del 20 nov 2026:** el proyecto es también el proyecto final de la materia de Bases de Datos (entrega a comienzos de diciembre de 2026). La v1 pasa a ser una **red social con verificación automática de cifras**: se puede publicar, seguir, comentar, reaccionar y ver tendencias, y las publicaciones que citan cifras de los 8 indicadores se verifican automáticamente contra el dato oficial. Lo anterior a esta fecha (la v1 de cuatro funcionalidades sin feed abierto) queda como antecedente. La materia exige Docker, subrutinas (procedimientos almacenados), funciones, transacciones, triggers y microservicios; se usan PostgreSQL y Neo4j.

### 1. La idea en una frase

Una red social colombiana donde cualquiera publica su opinión, y donde las publicaciones que citan cifras públicas quedan unidas automáticamente al dato oficial completo, para que nadie, de ningún lado político, consuma mentiras, medias verdades ni información ocultada.

### 2. Principios fijos

- **No busca cambiar opiniones ni despolarizar.** Busca que cada quien defienda sus ideas con información completa.
- **Misma vara para todos:** las mismas pruebas se aplican a cualquier afirmación, venga de quien venga. No se fuerza un 50/50 artificial; se publica la contabilidad por sector.
- **No dice "verdadero/falso":** dice si la conclusión se sostiene, se debilita o se invierte con el dato completo.
- **Regla de oro:** ningún número sale del sistema si no viene de una fuente oficial registrada.
- **Lo publicado no se calcula:** si la fuente oficial publica un valor (por ejemplo, la inflación mensual o la de año corrido), se toma de la fuente y no se calcula. Un cálculo solo se permite cuando la fuente no publica ese valor; se guarda como **"cálculo propio"** con la fórmula y los ids de las series usadas, y se muestra así al usuario.
- **Las opiniones se publican como opiniones:** no se verifican ni se califican. Solo se verifica lo que es una cifra sobre los 8 indicadores.
- **La verificación automática no inventa números:** la IA solo lee el texto de la publicación (qué indicador, qué periodo, qué valor dice); los valores oficiales, las comparaciones y la conclusión salen de la base y de reglas fijas. Si no hay dato comparable, se dice. Toda verificación muestra que es automática y cuál es su evidencia.
- **No se etiqueta políticamente a nadie:** ni usuarios ni publicaciones llevan un "lado". La diversidad de apoyos (tendencias) se mide con la estructura de la red, sin saber de qué lado está cada quien.
- **Orden de trabajo:** las bases de datos primero; la parte visual (app) es parte de la entrega del proyecto final, sobre bases ya probadas.
- **Alcance cerrado:** la v1 es la de la sección 3. Las ideas nuevas se anotan en el backlog (sección 7), no se meten en la v1.

### 3. Funcionalidades de la v1 (proyecto final)

1. **Red social.** Cuentas, perfiles, publicar opiniones, responder (hilos), compartir (repost), reaccionar, hashtags, mencionar figuras públicas, seguir y feed.
2. **Verificación automática de publicaciones.** Cuando una publicación cita una cifra sobre los 8 indicadores, el sistema la verifica solo: (1) la IA extrae la afirmación (indicador, variante, periodo, territorio, valor dicho); (2) reglas fijas la unen a la serie oficial o responden "sin dato comparable"; (3) se busca la observación oficial aceptada; (4) se aplican las pruebas de robustez (variante equivocada, periodo limitado, nominal frente a real, fuente distinta, dato provisional, notas de serie); (5) las reglas dan la conclusión (se sostiene / se debilita / se invierte / sin dato comparable); (6) la IA redacta la explicación en lenguaje neutral y un validador rechaza cualquier número que no esté en la evidencia. Lo que tenga baja confianza abre una alerta para revisión humana. Se mide contra el conjunto de prueba de 30 afirmaciones (meta: 24 de 30).
3. **Tendencias: temas del día y etiquetas** (decisión 17, diseño en `docs/diseno/06_temas_del_dia.md`). Es la funcionalidad central. (a) **Temas del día:** cada 3 horas se leen los medios colombianos registrados (RSS; GDELT de respaldo), la IA agrupa las noticias en temas y la base los ordena por cuántos medios distintos hablan de cada uno (mínimo 3; se muestran 5 a 7). De cada tema se extraen las declaraciones con cifras como las reporta el medio ("según [medio], [actor] dijo…", cita textual revisada por la base) y se verifican con el mismo motor: "esto se dijo; el dato oficial es este; la conclusión se sostiene / se debilita / se invierte", con las brechas de contexto encontradas. (b) **Etiquetas en tendencia dentro de la red**, con más peso cuando las usan personas que no están conectadas entre sí (grafo), y límites a cuentas nuevas o en revisión. La página de cada tema o etiqueta reúne las declaraciones verificadas, las publicaciones con cifras de la red y un resumen en conteos por conclusión (decisión 16). Todo sale de verificaciones guardadas: no hay resumen redactado por IA.
4. **Figuras públicas.** Perfil por figura con sus declaraciones y las verificaciones de esas declaraciones (máximo 10–15 figuras). Un administrador o verificador registra cada declaración con su fuente y sus temas (etiquetas); sus cifras pasan por la misma verificación automática que las publicaciones.
5. **Datos oficiales consultables.** La cifra oficial, su serie, su fuente y su trazabilidad hasta el archivo original (lo que ya existe).

6. **Comunidades** (decisión 28, 21 nov 2026): públicas o privadas, con papeles de administración separados y descubrimiento en Neo4j sin burbujas.
7. **Análisis de enlaces externos** (decisión 29, 21 nov 2026): una noticia vista en otra red o portal pasa por el mismo motor de verificación.

Fuera de la v1 (backlog): bot de WhatsApp, botón Compartir del celular, capturas de pantalla externas, temas de la semana elegidos por la comunidad y publicación en tiendas de aplicaciones.

### 4. Dominio de datos v1: Colombia, 8 indicadores

Economía: inflación, desempleo, salario mínimo, deuda pública. Seguridad: homicidios, hurtos, extorsión, secuestro. El detalle de fuentes y trampas está en el catálogo de abajo.

**Formatos de acceso verificados:**

| Fuente | Indicadores | Cómo se obtiene | Notas para el conector |
| --- | --- | --- | --- |
| Banco de la República, SUAMECA | Inflación anual, desempleo, salario mínimo (canal de acceso; la fuente oficial es la entidad original: DANE, MinTrabajo) | API JSON de la web de SUAMECA (`consultaMenuXId?idMenu=<id>`), no documentada; respaldo: descarga múltiple ([descarga múltiple](https://suameca.banrep.gov.co/descarga-multiple-de-datos/)). **El servicio SDMX oficial no sirve:** sus 33 flujos son tasas de interés, TRM, COLCAP, agregados monetarios, UVR y TES; no incluye estos indicadores (verificado el 25 oct 2026 contra la [guía técnica](https://suameca.banrep.gov.co/archivos/webservices/documento_tecnico_ws_consumo_sdmx.pdf) y el servicio en vivo) | La mejor fuente automatizable para economía. Al ser una API no documentada, se guarda siempre la respuesta original y el filtro 2 detiene la descarga si cambia la forma. No publica inflación mensual ni año corrido (vienen del DANE) ni deuda bruta del GNC (viene de MinHacienda). El servidor no envía el certificado intermedio (GeoTrust EV RSA CA G2): el conector lo incluye solo para el host suameca.banrep.gov.co (cualquier otro host usa el almacén de confianza estándar), la verificación TLS sigue completa y la prueba diaria avisa 90 días antes de que venza (2 jul 2030). Las fechas vienen a medianoche de Bogotá; en 1992-1993 (horario de verano en Colombia) algunas llegan a las 23:00 UTC−5. Referencia de uso: [banrepstats](https://github.com/fersalme/banrepstats) |
| DANE | IPC, GEIH | Anexos en Excel en la web ([IPC](https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc), [GEIH](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo)) y microdatos en el catálogo ANDA ([GEIH 2026](https://microdatos.dane.gov.co/index.php/catalog/900/related-materials)) | No hay API simple para los agregados: descarga programada de anexos. Usar el DANE como fuente oficial y SUAMECA para automatizar. Implementado (26 oct 2026): anexo "Variaciones porcentuales" (.xls hasta septiembre de 2026; desde octubre de 2026 el DANE lo publica en .xlsx con la misma estructura, y el lector acepta los dos formatos con la misma regla de decimales), anexo de la GEIH (.xlsx, sección "Total Nacional" de la hoja "Total nacional", que también trae "Total Cabeceras") y boletines técnicos del IPC desde 2023 (.pdf, texto con pdfminer.six). Los archivos se encuentran en su página cada vez (el nombre cambia cada mes) y se revisan a lo sumo una vez al mes con If-Modified-Since. El anexo no publica la variación anual de cada mes: sale de los boletines (y, antes de 2023, solo de diciembre). Fuentes en `catalog/sources/dane_publications.yaml` |
| Ministerio de Hacienda | Deuda del Gobierno Nacional Central | Portal de deuda pública con series desde 2019 ([MinHacienda](https://www.minhacienda.gov.co/deuda-publica)) e IRC ([IRC](https://www.irc.gov.co/en/public-debt/gnc-public-debt-profile)) | Confirmar el formato de descarga al construir el conector |
| Policía Nacional, SIEDCO | Homicidios, hurtos, extorsión, secuestro | Datos abiertos en datos.gov.co con API Socrata (SODA), p. ej. el dataset de homicidio ([datos.gov.co](https://www.datos.gov.co/Seguridad-y-Defensa/HOMICIDIO/m8fd-ahd9)); publicación mensual en la web ([Policía](https://www.policia.gov.co/estadistica-delictiva), "Cuadros de salida") | La API devuelve JSON/CSV. **Los datasets de datos.gov.co los publica MinDefensa** con origen SIEDCO (homicidio `m8fd-ahd9`, hurto a personas `4rxi-8m8d`, extorsión `q2ib-t9am`, secuestro `d7zw-hpf4`). Los datos son provisionales hasta marzo del año siguiente: guardar la fecha de corte de cada descarga |
| Ministerio de Defensa | Secuestro, extorsión (contraste) | Portal de información estadística ([MinDefensa](https://www.mindefensa.gov.co/defensa-y-seguridad/datos-y-cifras/informacion-estadistica)) | El portal requiere JavaScript; probablemente sea descarga manual o scraping. Fuente de contraste, no principal |

### 5. Arquitectura (proyecto final de Bases de Datos)

- **PostgreSQL:** fuente de verdad de todo lo transaccional (datos oficiales, usuarios, publicaciones, reacciones, seguidores, verificaciones, alertas). Aquí van los procedimientos almacenados, las funciones, las transacciones y los triggers.
- **Neo4j:** proyección de la red (quién sigue a quién, quién publicó, respondió, compartió o reaccionó, qué hashtags y figuras aparecen) para las consultas de varios saltos: feed, a quién seguir, difusión de una publicación y tendencias por diversidad. Se alimenta desde PostgreSQL con el patrón *transactional outbox* (un trigger escribe el evento en la misma transacción; el servicio de grafo lo aplica en Neo4j).
- **Microservicios (FastAPI, Python):** datos oficiales, social, grafo, verificación, IA y temas del día; cada uno con su propia base o esquema, detrás de una puerta de entrada (Nginx).
- **App:** solo web (decisión 15, 20 nov 2026): React + Vite + TypeScript, servida en Docker. iOS y Android quedan en el backlog.
- **Docker Compose:** levanta las bases, los servicios y la puerta de entrada.
- **Regla de diseño:** cada base detrás de una interfaz propia, para sumar o quitar motores sin rehacer la app.
- **Los modelos (entidad-relación y grafo) se definen y se aprueban antes de escribir el código de cada parte.**

### 6. Dónde vamos y qué sigue

- [x] Idea, principios y alcance v1 definidos
- [x] 8 indicadores elegidos
- [x] Catálogo de fuentes y trampas
- [x] Formatos de acceso verificados (falta confirmar MinHacienda y MinDefensa al construir)
- [x] Conjunto de prueba de 30 afirmaciones diseñado (falta cargarlo en la base)
- [x] Modelo de datos v1 diseñado (falta implementarlo en PostgreSQL)
- [x] Conectores de datos (Banco de la República y datos.gov.co primero), con pruebas contra valores de referencia. Hecho (25 oct 2026): interfaz común de conectores y conector de SUAMECA (inflación anual, desempleo, salario mínimo), con filtros 1 a 6 y pruebas; conector de datos.gov.co para homicidios con contraste contra publicaciones de la Policía; conector del DANE (inflación anual, mensual y año corrido; desempleo) con contraste en las dos direcciones contra SUAMECA. Primera corrida (26 oct 2026): sin cuarentena ni diferencias. Los conectores que faltan van en su propio punto, más abajo
- [x] PostgreSQL, primera migración (`db/migrations/0001_official_data.sql`, 26 oct 2026): bloque A del modelo de datos, contrastes y alertas; persistencia de observaciones, descargas, contrastes y alertas, más la copia sincronizada de fichas, aprobaciones y manifiestos. Base local con `docker-compose.yml`; corridas con `--db`. pgvector y los bloques B y C, después
- [x] Redefinición como red social con verificación automática (20 nov 2026)
- [x] Documento de diseño del proyecto final (`docs/diseno/`, 20 y 21 nov 2026): decisiones 1 a 20, MER, MR, DBML, grafo, lógica de la base, servicio de IA, temas del día y glosario. Falta: contratos de las APIs de los microservicios y diagramas en draw.io
- [x] Migración 0002 (21 nov 2026): esquemas `util` y `oficial`, tablas de 0001 renombradas al español sin perder datos, funciones, procedimientos y triggers de `oficial` (detalle en `db/LEEME.md`)
- [x] Migraciones 0003 (`social`) y 0004 (`ia`), 21 nov 2026, con sus pruebas
- [x] Migraciones 0005 (`temas`), 0006 (`verificacion`) y 0007 (roles por servicio), 21 nov 2026. Las 7 migraciones aplicadas y 280 pruebas sin conexión pasando (58 de ellas contra la base)
- [x] Diagramas (21 nov 2026, `diagramas/`): 3 MER en notación de Chen y 5 MR (uno por esquema, leídos de la base real), en draw.io y PNG, con el estilo del proyecto de biblioteca
- [x] Contratos de las APIs aprobados (21 nov 2026, decisiones 21 a 25)
- [x] Servicio social (FastAPI) y servicio de IA con dos proveedores (Groq: 2 cuentas; OpenRouter: modelos gratuitos de otros fabricantes) y extracción por consenso (decisión 26, migración 0008), 21 nov 2026
- [x] Motor de reglas (`docs/diseno/08_motor_de_reglas.md`) y servicio de verificación de punta a punta: filtro previo, dos lecturas con consenso, motor, explicación validada y API (migraciones 0009 y 0010), 21 nov 2026
- [x] Primera verificación real (21 nov 2026), base de desarrollo, Groq y OpenRouter de verdad: 6 publicaciones de demostración (usuario `demo_verificacion`), las 6 con la conclusión esperada y las dos lecturas coincidiendo en las 5 con cifras. Encontró que la IA podía agregar una brecha falsa con cifras correctas: corregido con la versión 2 del prompt de redacción
- [x] Servicios de datos oficiales y de temas del día (21 nov 2026). Primera corrida real: 400 artículos de 8 medios, 2 temas con 3 o más medios. Ajustes: identificadores cortos y hasta 20 titulares por medio (límite de 8.000 tokens por minuto de Groq gratuito); prompt de agrupación v2 para títulos neutrales ante denuncias e investigaciones
- [x] Docker Compose completo (21 nov 2026, `docs/diseno/09_docker.md`): 13 contenedores, una imagen para todos los servicios, cada uno con su rol de PostgreSQL, puerta de entrada Nginx que resiste servicios caídos, `restart: unless-stopped`. Probado: persistencia tras `down`/`up`, y la app sigue funcionando con Neo4j, la IA o un servicio detenidos. Encontró: las pruebas del grafo vaciaban el Neo4j de desarrollo (ahora usan uno aparte, perfil `pruebas`), y el consenso marcaba como distintos un mes escrito como días y como mes (ahora se normaliza)
- [x] App web Parrhesia (21 nov 2026, `web/`): logo en SVG fiel al original (dos P que se abren como mariposa), tema claro y oscuro, feed, publicar (barra superior y tecla N), detalle de verificación con gráfica de la serie oficial real y trazabilidad, temas del día, tendencias, figuras públicas, datos oficiales y revisiones. Servida por la puerta de entrada en http://localhost:8080
- [x] Entrar y crear cuenta en pantallas propias con panel vivo (Colombia en puntos, voces que se conectan, logo que se abre y datos oficiales reales rotando) y acceso seguro (migración 0012, `docs/diseno/09_docker.md`): cookie `HttpOnly`, sesiones que se cierran en el servidor, protección CSRF, límite de intentos y cabeceras de seguridad
- [x] Segunda etapa, T1 tipografía (21 nov 2026, decisión 32): sistema "Claridad" (Bricolage Grotesque + Atkinson Hyperlegible Next + Atkinson Hyperlegible Mono), elegido entre seis propuestas comparadas con el dato real; se quitan los filetes decorativos antes de los títulos
- [x] Segunda etapa, T2 logo (21 nov 2026): símbolo mariposa redibujado sobre la referencia (contorno medido, ala derecha en espejo exacto), fuente única `web/src/marca.ts` y generador `npm run marca` (favicon, ícono de app claro y oscuro, logos negro y crema); aleteo sutil en el acceso y al pasar en la barra lateral, quieto con "reducir movimiento"
- [x] Segunda etapa, T3 acceso (21 nov 2026): relieve real de Colombia en puntillismo (NOAA ETOPO1 + Natural Earth, dominio público, `web/scripts/generar_relieve.py`) sobre un plano en perspectiva con paralaje leve, mariposas con la forma del logo, eslogan "La palabra es tuya. El dato, de todos." y sin datos oficiales en el acceso
- [x] Segunda etapa, T4 tono y tema (21 nov 2026): guía `docs/diseno/10_tono_y_lenguaje.md` (tono editorial sereno, vocabulario fijo neutral) aplicada a pantallas, avisos, estados y errores del backend; eslogan "La palabra es tuya. El dato, de todos."; interruptor de tema propio (ficha con el logo, alas que se pliegan de noche, sol y estrellas de puntos), en el pie de la barra lateral y en la barra superior en celular, sincronizado entre pestañas
- [x] Segunda etapa, T5 estadísticas (21 nov 2026): fichas de dato con la cifra protagonista, valores publicados del periodo anterior y de un año antes (solo la dirección, nunca una diferencia calculada), línea de valores reales, fuente con nombre legible del canal, fecha de actualización normalizada, avisos de dato provisional y notas vigentes; la API de datos oficiales entrega ese resumen (`resumen` en `/v1/series`) con reglas compartidas en `servicios/comun/reglas_datos.py`; sin franjas de color en veredictos, avisos ni citas
- [x] Segunda etapa, T6 temas (21 nov 2026, migración 0013): pila de temas desplegables en la columna derecha del inicio (el feed queda al centro; una ficha abierta a la vez, con teclado; cada elemento visual informa: anillo de medios que cubren, actividad real por tramos de 3 horas; sin animaciones decorativas) y página "Temas del día" sin numeración: cada tema con su huella, los medios que lo cubren por nombre y su actividad
- [x] Segunda etapa, T7 perfil y búsqueda (21 nov 2026, migraciones 0014 y 0015): panel lateral para editar nombre visible, nombre de usuario (disponibilidad en vivo; una vez cada 30 días; el anterior sigue llevando al perfil y nadie más lo toma), biografía, foto (re-codificada a WebP 400 × 400 sin metadatos, volumen `fotos`), correo y contraseña (con la actual; cierra las otras sesiones) y desactivación (decisión 30); búsqueda de personas con `pg_trgm` y página `/buscar`
- [x] Segunda etapa, T8 editor (21 nov 2026, migraciones 0016 y 0017): negrita, cursiva y enlaces https (con su dominio siempre visible) como marcas de texto, nunca HTML; autocompletado de @personas y figuras públicas; etiquetas; contador de lo visible (500) igual al de la base; vista previa; atajos de teclado. Etiquetas, menciones y verificación usan el texto plano (probado con una verificación real: "Se sostiene")
- [x] Segunda etapa, T9 404 y rutas (21 nov 2026): página 404 con una cara hecha con el número (los 4 son los ojos, el 0 la nariz, la mariposa del logo posada encima; la boca se dibuja, los ojos parpadean, la mariposa aletea una vez) y su variante 403; rutas inexistentes, ids que no existen o mal formados (perfil, publicación, serie, dato, figura, tema) llevan a ella en vez de quedarse cargando; `/revisiones` protegida por rol, entrar devuelve a donde ibas y "Entrar" con sesión lleva a la app
- [x] Segunda etapa, T10 comunidades en PostgreSQL (21 nov 2026, migración 0018, decisión 28): públicas y privadas, solicitudes, papeles separados (administrador, gestor de integrantes, moderador), nunca sin administrador (probado con dos degradaciones simultáneas), bitácora de solo inserción, visibilidad decidida en la base y aplicada en feed, perfil, hilo, tendencias y verificación; páginas de comunidades con administración
- [x] Segunda etapa, T10a figuras públicas (21 nov 2026, migración 0019): solo verificadores y administradores crean y editan; cualquiera propone y un verificador decide; cada dato con fuente oficial (el partido solo con fuente y nunca para agrupar); sin duplicados escritos distinto; fichas archivables; bitácora pública con antes y después; registrar declaraciones desde la ficha
- [x] Segunda etapa, T11 comunidades en Neo4j (21 nov 2026, migración 0020): proyección mínima (Comunidad, INTEGRA, EN; papeles solo en PostgreSQL), reconstrucción idéntica; lo privado no alimenta tendencias, feed ni sugerencias; descubrimiento sin burbujas (comunidades sugeridas fuera de mi red, comunidades que hablan de lo mismo con menos personas en común, otras voces fuera de mi red), cada sugerencia con su porqué
- [x] Segunda etapa, T12 análisis de enlaces externos (21 nov 2026, migraciones 0025 y 0026, decisión 29): se pega un enlace o un texto en "Analizar enlace"; la página se lee en memoria (solo http(s), nunca direcciones internas ni después de una redirección, 2 MB, 15 s, respeta robots.txt; X, Facebook, Instagram, TikTok y similares piden el texto) y solo se guardan los metadatos que declara y las citas cortas que pasan el filtro previo en la base; cada cita va por el mismo consenso, motor, validador y revisión humana. La IA nunca recibe el texto completo (probado). Límite de 10 análisis por hora y por persona y reutilización de análisis idénticos, en la base. Probado con tres notas reales (Infobae, Caracol Radio, El Tiempo). Pendiente conocido: la dirección se revisa antes de conectar, pero no se fija la IP para la conexión (DNS rebinding); aceptable para la v1 en desarrollo
- [x] Datos de demostración sin IA (21 nov 2026, `db/semillas/demo.py`): 40 personas ficticias, 11 comunidades, unas 380 publicaciones en 45 días, tendencias calculadas por el grafo; `--resembrar` el día de la presentación. Encontró que una compartida sin comentario se veía "pendiente" para siempre: corregido con la migración 0024
- [x] Evaluación de la verificación automática (T14, 21 nov 2026, `evaluacion/`): línea base 22 de 30 (con dato oficial 1 de 7); después de las correcciones (decisión 33, prompt v2, motor sin comparar cambios con el nivel, notas de todas las series) **27 de 30** (meta 24; con dato 6 de 7). Conjunto de control de 10 afirmaciones nuevas, fijado antes de correr: **9 de 10** (meta 8). Los dos fallos quedan en revisión humana, sin conclusión publicada: la fila 17 (no señala la variante de 0,39 %) y la 7 del control (las lecturas no coinciden en el periodo). La evaluación encontró dos fallas de robustez, corregidas: un periodo leído al revés pasaba el validador de la IA y la base lo rechazaba, y ese rechazo detenía la cola de verificación (ahora el validador lo rechaza y un texto que la base rechaza queda en revisión sin detener a los demás); y el trabajador del grafo se caía si se reiniciaba dentro de la misma hora en que ya se habían calculado las tendencias. Las corridas incompletas quedan en `evaluacion/resultados/` marcadas como tales
- [x] Coherencia de la red (22 nov 2026, migración 0027): el inicio muestra publicaciones y compartidas, no respuestas sueltas (se leen en su hilo, en Neo4j y en el respaldo de PostgreSQL); una respuesta dice a quién responde y una compartida muestra la publicación original con su conclusión; compartir es una sola vez por persona y volver a pulsar deshace (antes cada clic creaba otra). La demo suma 11 publicaciones verificadas con todas las conclusiones (`--cifras`)
- [x] Mejora visual (22 nov 2026, migraciones 0028 a 0030): estilo cálido y redondeado (claro y oscuro), buscador alineado con el feed, separador difuminado de la columna derecha, tarjetas con avatar a la izquierda y la conclusión al pie con acceso al análisis, conteos de Me gusta y Útil, "A quién seguir" con botón Seguir, Publicar flotante, la cuenta del menú lleva al perfil; temas del día en carrusel con imagen de Unsplash (crédito del fotógrafo, búsquedas por reglas fijas sin nombres propios); avatares ilustrados para la demo; Datos oficiales sin series repetidas (la misma serie por otro canal se nombra como contraste)
- [x] Guías de lectura (22 nov 2026, migraciones 0031 a 0033, decisión 34): cada análisis dice por qué y cómo comprobarlo ("Para entenderlo", "Compruébalo tú" con la página oficial), también sin dato comparable y en revisión; la IA redacta la guía y solo se publica si un juez de otro proveedor la aprueba; "Cómo leer este tema" en los temas del día; verificaciones de otros medios cuando haya llave de Google. Conjunto de 15 casos (`evaluacion/afirmaciones_guias.yaml`) fijado antes de correr; se corre cuando haya cupo de OpenRouter
- [x] Figuras públicas reales (22 nov 2026, `db/semillas/figuras.py`): 13, elegidas por relevancia y equilibrio entre gobierno, oposición, centro e instituciones técnicas y de control; cada cargo con su fuente https; sin partido ni ninguna etiqueta política (el equilibrio es solo un criterio para elegir). Debates en la demo con posturas defendidas
- [x] Declaraciones reales (22 nov 2026, `db/semillas/declaraciones.py`): 7 citas de 4 figuras, copiadas tal cual de lo que el medio pone entre comillas (lo parafraseado no se registra), con la fecha de la intervención y su enlace; elegidas para mostrar los desenlaces sin forzarlos (comparables, local, otra serie, proyección, condicional). Para las otras 9 figuras no se halló una cita textual con cifras de los indicadores cargados: no se les atribuye nada
- [x] Modo demostración (22 nov 2026, `web/src/datos/demostracion.ts`, `MODO_DEMO=1` por defecto en Compose): "Ejemplo al azar" en publicar y responder, y "Noticia de ejemplo" / "Texto de ejemplo" en Analizar; solo llenan el campo, la persona decide si publica. Las noticias son reales y el lector las pudo leer; `MODO_DEMO=0` quita los botones
- [x] Tiempos de respuesta (22 nov 2026, migración 0034, decisión 35): análisis de enlaces en segundo plano con aviso, reloj y "Ver" al terminar; un hilo de IA por proveedor; cola con prioridad; Gemini como segundo lector cuando haya llave (`GEMINI_KEY_gemini_1`)
- [x] Roles con bitácora (22 nov 2026, migración 0035, decisión 36): procedimiento para asignar roles, bitácora pública, al menos un administrador, primer administrador por consola (@dubal_aguilar) y página Equipo
- [ ] **Siguiente:** auditoría, correr el conjunto de guías y presentación
- [x] DANE: el anexo de variaciones del IPC pasó a `.xlsx` desde octubre de 2026 (filtro 2); el lector acepta los dos formatos y se cargaron octubre de 2026 (IPC) y septiembre de 2026 (GEIH) (21 nov 2026)
- [ ] Homicidios con cambios en la fuente (21 nov 2026): datos.gov.co da 1.203 para agosto de 2026 (referencia: 1.190, filtro 4); los Cuadros de salida traen datos hasta octubre con la fecha de publicación anterior; el registro 2026 cambió de formato y el anual pasó de .zip a .xlsx. **Decisión (21 nov 2026):** la base conserva 1.190 (último valor publicado con fecha coherente, provisional) y la referencia no cambia hasta que la Policía publique un archivo con fecha de publicación coherente con su corte; no se supone la fecha de corte. Lectores al día (21 nov 2026): el registro 2026 de noviembre (DELITOS, segunda columna MES con el nombre del mes que debe coincidir, sin pie con fecha de entrega) se lee y coincide mes a mes con los Cuadros de salida (enero 1.207 … octubre 1.059); el anual en .xlsx ya se leía. Solo falta que la fecha de publicación de los Cuadros sea coherente
- [x] Neo4j 5.26 en Docker y servicio de grafo (21 nov 2026, `src/servicios/grafo/`): sincronizador del outbox con entrega por consumidor, feed, a quién seguir, difusión, tendencias por diversidad, reconstrucción desde PostgreSQL y API; 10 pruebas contra Neo4j. Diagramas NEO4J_1 y NEO4J_2
- [ ] Servicio de temas del día: medios registrados, recolección de artículos, agrupación en temas y extracción de declaraciones con cita textual
- [ ] Verificación automática de publicaciones, medida contra el conjunto de prueba de 30 afirmaciones
- [ ] App web (React + Vite + TypeScript)
- [ ] Docker Compose completo y presentación
- [ ] **Prioridad alta, después de PostgreSQL:** flujo de revisión humana de alertas: que una persona revise y cierre las marcas que requieren revisión (salto, cambio de un valor definitivo, contraste que no coincide, y la alerta obligatoria cuando SUAMECA y el DANE no coinciden) y quede registro de quién, cuándo y por qué. Necesita las alertas guardadas en la base. Hoy esas marcas se mantienen hasta que el valor cambie y el dato sigue en cuarentena; sin este flujo, el motor no puede usar con respaldo humano un valor del DANE que difiere de SUAMECA
- [ ] Conectores que faltan: MinHacienda (deuda pública), MinDefensa (contraste de secuestro y extorsión) y los demás delitos de datos.gov.co (hurtos, extorsión, secuestro)
- [x] Carga del conjunto de prueba de 30 afirmaciones (es también la evaluación de la verificación automática): ver T14

**Pendiente al crear el repositorio en GitHub: glosario de terminología neutral.** Regla: describir lo que pasa con el dato, nunca la intención de quien lo dijo. Ejemplos acordados: "trampa" → "brecha de contexto"; "periodo a conveniencia" → "periodo de comparación limitado"; "incorrecto" → "no coincide con la fuente"; "cuenta sospechosa" → "cuenta en revisión"; nunca "mentira", "engaño" ni "manipulación". Mientras sea proyecto de la materia, el código va en español sin tildes (decisión 14, `docs/diseno/glosario_codigo.md`); al pasar a open source se vuelve al inglés con ese glosario. El modelo de datos de este documento usa todavía los términos de trabajo y se renombra al aplicar el glosario.

### 7. Backlog (ideas aplazadas, no entran en la v1)

Bot de WhatsApp · contraste de declaraciones con registros oficiales no numéricos (decretos, leyes, votaciones, documentos firmados) · botón Compartir del celular · radiografía de enlaces y capturas externas · temas de la semana elegidos por la comunidad · publicación en tiendas de aplicaciones · apps para iOS y Android · video y audio · detección de deepfakes · alertas de seguimiento · explorador de datos · módulo de aprendizaje de trampas · cobertura regional · otros países · validación humana con bridging (opcional, como control de calidad) · lectura de los boletines técnicos del IPC anteriores a 2023 (PDF con formatos que cambian por época) para ampliar el contraste mensual de la inflación anual y el año corrido · compartir el análisis de un enlace como publicación · leer PDF, imágenes o video de un enlace · analizar los enlaces que vienen dentro de las publicaciones · fijar la IP resuelta al descargar un enlace (DNS rebinding) · contexto con el último dato oficial en opiniones sin cifra que mencionan un indicador (decisión 34, roza "las opiniones no se verifican").

## Conjunto de prueba v1: 30 afirmaciones (25 oct 2026)

Sirve para medir el motor de radiografía antes de abrirlo al público. **Las columnas "Hipótesis" no son veredictos**: son lo que esperamos que el motor encuentre y se confirman descargando el dato oficial. Las filas 17, 20 y 28 a 30 son plantillas: la 17 y la 20 se construyeron con datos reales del DANE, y a la 28, la 29 y la 30 todavía les falta un caso real.

**Cómo usarlo:** guardar cada fila en la base (texto exacto, enlace, fecha, quién lo dijo), correr el motor y comparar con la hipótesis. Meta inicial: que el motor detecte la trampa principal en al menos 24 de 30.

| # | Afirmación | Indicador | Origen | Trampas a revisar | Hipótesis |
| --- | --- | --- | --- | --- | --- |
| 1 | El secuestro bajó 79 % en el primer mes de gobierno (agosto 2026 vs agosto 2025) | Secuestro | Alocución presidencial, reportada por El Colombiano, El Universal y CRprensa | Un solo mes, base pequeña, datos provisionales | Por confirmar con SIEDCO y MinDefensa |
| 2 | La extorsión cayó 62–63 % | Extorsión | Presidencia | Elegir la fuente conveniente: la Policía reporta −39 % y MinDefensa −43 % (Yahoo/AFP) | Se debilita |
| 3 | Las masacres cayeron 58 % | Homicidios | Presidencia | Base pequeña, definición de masacre | Por confirmar |
| 4 | Los homicidios bajaron 64 % en los primeros 30 días | Homicidios | Presidencia, según Headtopics | Periodo a conveniencia, fuente, provisional | Por confirmar; cifra muy alta, revisar |
| 5 | Los hurtos bajaron 24 % | Hurtos | Presidencia | La Policía registra −18 % y MinDefensa −36 % (solo hurto a personas); modalidades mezcladas | Se debilita o cambia según la modalidad |
| 6 | En agosto 2026 hubo 499 homicidios (MinDefensa) frente a 717 (Policía) | Homicidios | Informe de Racero, según El Tiempo | Dos fuentes que miden distinto | Caso para enseñar las diferencias entre fuentes. Nota (25 oct 2026): ni 717 ni 499 coinciden con los 1.190 homicidios intencionales de agosto 2026 de los Cuadros de salida de la Policía (publicados el 20 oct 2026, provisionales); hay que averiguar qué periodo o definición usan |
| 7 | El hurto a personas cayó 49 % | Hurtos | El País | Denuncias frente a delitos, un mes | Por confirmar con la encuesta del DANE |
| 8 | Las denuncias de extorsión cayeron 46 % | Extorsión | El País | Menos denuncias no significa menos delitos | Se debilita si no hay contraste |
| 9 | Reducción de homicidios en Barranquilla presentada por el presidente | Homicidios | Yahoo/AFP | Absolutos sin tasa, periodo corto | Por confirmar |
| 10 | El salario mínimo subió 23,7 % en 2026 | Salario mínimo | Decreto 1469 de 2025 y prensa | Nominal frente a real | Se sostiene en lo nominal; falta el dato real. Nota (25 oct 2026): la serie de SUAMECA da $1.750.905 frente a $1.423.500 (23,0 %), y el Decreto 1469 de 2025 dice textualmente "un incremento del veintitrés por ciento (23%)" (Diario Oficial 53.350); el Decreto 0159 de 2026 repite el 23 %. El 23,7 % aparece en prensa, no en el decreto; revisar la hipótesis con el porcentaje oficial |
| 11 | El gobierno anterior recibió el mínimo por debajo del millón y lo dejó en $1.750.905 | Salario mínimo | Radio Nacional | Pesos nominales sin descontar la inflación de 4 años | Se debilita si no se ajusta |
| 12 | El aumento supera en 17,9 pp la inflación de 2025 (5,10 %) | Salario mínimo + inflación | Fedesarrollo | Comparar porcentajes nominales; restar no da la variación real exacta | Se sostiene con matiz técnico |
| 13 | El aumento del mínimo dejará a X personas sin trabajo | Salario mínimo + desempleo | Fedesarrollo | Proyección presentada como hecho | Se marca como proyección, no como dato |
| 14 | Fue el mayor aumento desde la Constitución de 1991 | Salario mínimo | El Cronista | Nominal frente a real; serie histórica completa | Por confirmar con la serie del BanRep |
| 15 | El Consejo de Estado cuestionó el aumento con inflación cercana al 5 % y productividad menor al 1 % | Salario mínimo + inflación | El Cronista | Cifras redondeadas, fuente de la productividad | Por confirmar |
| 16 | La inflación anual de septiembre 2026 fue 6,29 %, 1,11 pp más que un año antes | Inflación | DANE, vía Infobae | Mezclar mensual, año corrido (5,74 %) y anual | Se sostiene |
| 17 | La inflación de agosto fue 0,39 % (presentada como "inflación bajísima") | Inflación | Plantilla basada en el dato del DANE | Mensual presentada como anual (la anual fue 6,24 %) | Se invierte |
| 18 | Analistas proyectaban 6,33 % para septiembre | Inflación | Citi, vía Infobae | Proyección frente a dato observado (6,29 %) | Se marca como proyección |
| 19 | El desempleo de julio 2026 fue 8,1 %, 0,7 pp menos que en 2025 | Desempleo | DANE | Comparación anual correcta; revisar la participación | Se sostiene |
| 20 | "El desempleo se disparó" al pasar de 8,1 % en julio a 9,4 % en agosto | Desempleo | Plantilla basada en datos del DANE | Estacionalidad: comparar meses distintos | Se debilita. Nota (25 oct 2026): según el anexo de la GEIH, para agosto de 2026 el DANE ajustó los factores de expansión por el sismo del 10 de agosto de 2026 (nota de serie `earthquake_adjustment_2026_08`); el motor debe citarlo sin estimar cuánto pesó el ajuste |
| 21 | Las relaciones laborales dependientes bajaron 0,4 % mientras baja el desempleo | Desempleo | DANE (RELAB) | Medidas distintas (registros frente a encuesta) | Caso para explicar por qué ambas cosas pueden ser ciertas |
| 22 | La deuda pública llegó a un récord de $1.238,2 billones en febrero 2026 | Deuda pública | MinHacienda, vía Yahoo | Pesos nominales frente a % del PIB | Se sostiene en pesos; el contexto es el % del PIB |
| 23 | En enero la deuda equivalía al 65 % del PIB y en febrero al 62,9 % | Deuda pública | Prensa con datos de MinHacienda | Cambio del PIB proyectado usado como denominador | Revisar el denominador |
| 24 | La deuda bajó al 60,6 % del PIB en mayo | Deuda pública | Valora Analitik | PIB proyectado, bruta frente a neta | Por confirmar |
| 25 | La deuda externa bajó del 41,8 % (2022) al 24,1 % (2026) | Deuda pública | MinHacienda/Presidencia | Externa frente a total; base de comparación | Por confirmar qué mide el porcentaje |
| 26 | La deuda neta está alrededor del 57 % del PIB | Deuda pública | MinHacienda | Neta frente a bruta (bruta \~60–63 %) | Se sostiene si se aclara que es neta |
| 27 | La deuda total es de US$370.000 millones | Deuda pública | Prensa | Dólares frente a pesos, efecto de la tasa de cambio | Revisar la conversión |
| 28 | Plantilla: gráfica de homicidios con el eje Y recortado para exagerar la caída | Homicidios | Por buscar caso real | Eje recortado | — |
| 29 | Plantilla: "la inseguridad está peor que nunca" citando una encuesta de percepción | Hurtos | Por buscar caso real | Percepción frente a registros | — |
| 30 | Plantilla: inflación de alimentos presentada como inflación total | Inflación | Por buscar caso real | Subcomponente frente a índice total | — |

## Modelo de datos v1 (25 oct 2026)

Primera versión para construir. Todo vive en **PostgreSQL** salvo lo que se indique. Las columnas `embedding` usan **pgvector**. Convención: cada tabla tiene `id` (UUID), `creado_en` y `actualizado_en`.

### Bloque A. Datos oficiales (el corazón de la regla de oro)

| Entidad | Para qué sirve | Campos clave |
| --- | --- | --- |
| `fuente` | Entidad oficial registrada (DANE, BanRep, Policía, MinDefensa, MinHacienda, MinTrabajo) | nombre, tipo\_acceso (API JSON, SODA, Excel, manual), url\_base, nivel (principal o contraste) |
| `indicador` | Los 8 indicadores | nombre, categoría (economía o seguridad), unidad, frecuencia, fuente\_principal\_id |
| `serie` | Una forma concreta de medir un indicador | indicador\_id, fuente\_id (entidad que produce el dato), canal\_acceso\_id (entidad que lo distribuye, si es otra: BanRep para datos del DANE, MinDefensa para datos SIEDCO), código\_externo (ej. id de serie SUAMECA o id del dataset Socrata), variante (anual, mensual, año corrido, tasa por 100.000, nominal, real, bruta, neta), cobertura geográfica |
| `descarga` | Cada vez que se trae una serie | serie\_id, fecha\_corte, fecha\_descarga, archivo\_original (hash y ruta), estado (provisional o definitivo) |
| `observacion` | Cada valor de una serie | serie\_id, descarga\_id, periodo, territorio, valor. **Nunca se sobrescribe**: si el dato cambia, entra una fila nueva con otra descarga (append-only) |
| `nota_serie` | Contexto con rango de fechas que el motor cita si una afirmación cae en ese periodo (ej. "decreto suspendido", "decreto transitorio 0159", "suspensión revocada", cambio de metodología, fe de erratas). No cambia ningún valor de la serie | serie\_id, desde, hasta (vacío si sigue vigente o no está confirmado), tipo (legal, metodológica, fe de erratas), texto, documento\_fuente (url, hash, fecha de consulta), estado (confirmada, pendiente de fuente oficial o fuentes oficiales en conflicto: en este último caso se registran todas las fuentes con su cita, sin elegir) |
| `trampa` | Catálogo de trampas con nombre propio | código, nombre, explicación, prueba\_asociada |

### Bloque B. Radiografía

| Entidad | Para qué sirve | Campos clave |
| --- | --- | --- |
| `contenido` | Lo que llega (enlace, texto o captura) | tipo, texto\_extraído, url, hash, canal (app, WhatsApp, compartir), usuario\_id |
| `afirmacion` | Cada afirmación detectada | contenido\_id, texto, tipo (dato, interpretación u opinión), indicador\_id, `embedding` |
| `radiografia` | El análisis de una afirmación | afirmacion\_id, conclusión (se sostiene, se debilita o se invierte), confianza, texto\_explicativo, versión\_del\_motor |
| `radiografia_observacion` | Qué datos oficiales usó (trazabilidad) | radiografia\_id, observacion\_id, rol (dato citado o dato completo) |
| `radiografia_trampa` | Qué trampas encontró | radiografia\_id, trampa\_id, detalle |
| `caso_prueba` | El conjunto de las 30 afirmaciones | afirmacion\_id, hipótesis, resultado\_obtenido, acierto |

### Bloque C. Temas, figuras públicas y comunidad

| Entidad | Para qué sirve | Campos clave |
| --- | --- | --- |
| `tema` | Los 10 temas de la semana | semana, título, origen (automático o comunidad), resumen |
| `tema_afirmacion` | Afirmaciones que forman un tema | tema\_id, afirmacion\_id |
| `sugerencia` | Propuestas de la comunidad | usuario\_id, texto, `embedding`, grupo\_id |
| `apoyo` | Quién apoya cada sugerencia | sugerencia\_id, usuario\_id, peso (según diversidad y antigüedad) |
| `figura_publica` | Las 10–15 figuras | nombre, cargo, partido |
| `declaracion` | Lo dicho o prometido | figura\_id, texto, fecha, tipo (declaración o promesa), afirmacion\_id, estado\_promesa |
| `usuario` | Cuentas | teléfono\_whatsapp, fecha\_alta, reputación\_precisión, estado (normal o sospechosa) |
| `comentario` | Debate anclado | usuario\_id, tema\_id o radiografia\_id, padre\_id, texto, tipo (dato o valor) |
| `etiqueta_cifra` | Etiqueta automática de cifras en comentarios | comentario\_id, cifra, estado (con fuente, sin fuente, incompleta o incorrecta), observacion\_id |
| `voto` | Votos a comentarios | comentario\_id, usuario\_id, valor |

### Relaciones principales

- Una `fuente` publica muchas `serie`; un `indicador` tiene muchas `serie`.
- Una `serie` tiene muchas `descarga` y cada una trae muchas `observacion`.
- Una `serie` tiene muchas `nota_serie`; el motor cita las que se cruzan con el periodo de la afirmación.
- Un `contenido` produce muchas `afirmacion`; cada `afirmacion` tiene como máximo una `radiografia` vigente (las versiones anteriores se guardan).
- Una `radiografia` cita muchas `observacion` y muchas `trampa` (tablas puente).
- Un `tema` agrupa muchas `afirmacion`; una `declaracion` puede convertirse en `afirmacion` para radiografiarla.

### Qué va en cada base

- **PostgreSQL:** todo lo anterior. Implementado hasta ahora (migración 0001): el bloque A con nombres en inglés (`fuente` → `source`, `indicador` → `indicator`, `serie` → `series`, `descarga` → `download` + `raw_file`, `observacion` → `observation`, `nota_serie` → `series_note`, `trampa` → `context_gap`), más `series_approval`, `known_version_difference`, `evidence_file`, `contrast_check`, `alert` y `alert_event`. Los valores van en `NUMERIC` (decimal exacto). `observation`, `download`, `raw_file`, `contrast_check`, `alert_event`, `series_approval` y `evidence_file` son de solo inserción (un trigger impide modificarlas o borrarlas); en `alert` solo puede cambiar el estado. Las migraciones son archivos SQL numerados que no se modifican una vez aplicados (`uv run python -m app.db.migrate`). La migración 0002 mueve estas tablas al esquema `oficial` y las renombra al español (decisión 14).
- **pgvector:** `afirmacion.embedding` (encontrar radiografías ya hechas) y `sugerencia.embedding` (agrupar sugerencias).
- **Opcional, según el enunciado del I+D:** grafo para usuarios y difusión de contenidos; base de series de tiempo para `observacion` (por ejemplo, TimescaleDB, que también es PostgreSQL); Redis como caché de los temas de la semana.

### Decisiones de diseño

- **Trazabilidad total:** toda cifra que muestre la app debe poder seguirse hasta una `observacion`, su `descarga` y su archivo original.
- **Versionado:** los datos provisionales de la Policía cambian hasta marzo; por eso `observacion` es append-only y la radiografía guarda qué descarga usó. La Policía dice que los datos "son provisionales y solo hasta marzo del siguiente año pasarán a ser definitivos". **Interpretación nuestra, no regla oficial de la Policía:** un periodo del año A se trata como definitivo desde el 1 de abril del año A+1; desde esa fecha, un cambio en su valor dispara la alerta del filtro 6.
- **Fuente de verdad: git o PostgreSQL.** Git es la fuente de verdad de las fichas (`catalog/series/`), sus aprobaciones (bloque `approval` con `content_sha256`), la configuración de fuentes de contraste (`catalog/sources/`) y los manifiestos de evidencia (`evidence/`); la base guarda una copia sincronizada en cada corrida y nunca se edita a mano. PostgreSQL es la fuente de verdad de las observaciones, las descargas, los contrastes y las alertas con su historial de revisión (quién, cuándo y por qué); eso no se guarda en git. Si la copia de la base no coincide con git (por ejemplo, una ficha cambió y su hash ya no es el aprobado), manda git y la serie no se conecta hasta que se apruebe de nuevo.
- **Decimal exacto, nunca float:** todo valor se guarda como decimal exacto tal como lo publica la fuente. JSON se lee con números decimales (no float); en un .xlsx se usa el texto del número escrito en la celda (el XML del archivo; si el archivo escribe el doble con 17 cifras, como el anexo del IPC en .xlsx desde octubre de 2026 —"1.1100000000000001"—, se aplica la misma regla que al .xls), no la conversión a float de la librería; un .xls (formato binario antiguo) guarda el número como binario de doble precisión, así que se toma la representación decimal más corta que reproduce exactamente ese número (para el anexo del IPC, que publica 2 decimales, da el valor publicado, por ejemplo 0,39), y la ficha lo registra.
- **Archivos en git:** los archivos originales descargados no van a git (`data/`); en el repositorio quedan solo sus hashes y metadatos (`evidence/`). Excepción: los fixtures de prueba con datos públicos reales pueden ir a git si pesan hasta 1 MB por archivo (por ejemplo, las respuestas de SUAMECA en `tests/fixtures/`). Los originales más grandes siguen fuera y las pruebas usan extractos sintéticos con el mismo formato.
- **Series separadas por variante:** inflación anual, mensual y año corrido son series distintas, para que el motor no pueda mezclarlas sin darse cuenta.
- **Cálculo propio separado:** un valor calculado (solo cuando la fuente no lo publica) se marca como cálculo propio y guarda la fórmula y los ids de las series de entrada; nunca se presenta como dato de la fuente.

## Conectores de datos y verificación de calidad (25 oct 2026)

Objetivo: que el sistema nunca use un dato equivocado ni uno que no corresponda a lo que se está analizando. Si un dato no pasa todas las verificaciones, **no se usa**; el sistema prefiere decir "no hay dato comparable" antes que aproximar.

### Primeros dos conectores

| Conector | Cómo funciona | Qué guarda | Prueba de que funciona |
| --- | --- | --- | --- |
| Banco de la República (SUAMECA) | API JSON de la web de SUAMECA: se pide un menú por su id y devuelve JSON con las series históricas y sus metadatos (fuente original, fecha de último cargue, ficha técnica). El servicio SDMX no tiene estos indicadores. Respaldo: descarga múltiple en archivo | Respuesta original, hash, fecha de descarga y valores | Descargar la inflación anual, el desempleo y el salario mínimo y compararlos con los valores de referencia de abajo |
| Datos SIEDCO (datos.gov.co) | API Socrata (SODA): `https://www.datos.gov.co/resource/<id>.json`, con filtros por fecha y paginación; usar token de aplicación para no ser limitado | Archivo original, fecha de corte, estado provisional o definitivo. Además, cada versión del archivo "Cuadros de salida" de la Policía (se reemplaza cada mes en la misma URL) se guarda con fecha de descarga y hash, como evidencia de los valores de referencia | Contar homicidios de agosto 2026 y compararlos con el total de los Cuadros de salida de la Policía (1.190, publicado el 20 oct 2026, provisional) |

Luego: DANE (descarga programada de anexos en Excel), MinHacienda y MinDefensa (confirmar formato; posible carga manual con evidencia).

### Protocolo de verificación: siete filtros

1. **Ficha de cada serie, aprobada por una persona.** Antes de conectar una serie se registra su definición oficial, unidad, metodología, código y variante (mensual, anual, tasa, nominal, real…). Nadie la conecta "porque se parece". La aprobación queda atada al contenido: al aprobar, la persona guarda en el bloque `approval` el `content_sha256` de la ficha, calculado sobre el texto del archivo sin el bloque `approval` y con los comentarios incluidos (`uv run python -m app.catalog <código>` lo imprime). Si la ficha cambia después, el hash ya no coincide y el pipeline no conecta la serie hasta que se apruebe de nuevo.
2. **Forma del archivo.** Al descargar se revisa que estén las columnas esperadas, con los tipos y unidades correctos. Si la fuente cambia el formato, la descarga se detiene.
3. **Valores plausibles.** Rangos razonables (por ejemplo, desempleo entre 0 % y 30 %), sin meses faltantes ni duplicados y sin saltos imposibles. Un valor fuera de rango o con un salto mayor al de su ficha **queda en cuarentena para revisión**: no se rechaza ni se borra, pero no se usa hasta que una persona lo revise. El filtro de saltos aplica solo a observaciones nuevas, no a la carga inicial del historial; los saltos históricos conocidos se registran en la ficha como excepciones documentadas (`known_exceptions`), con su explicación y, cuando exista, la fuente oficial.
4. **Valores de referencia.** Cada serie se compara con cifras publicadas oficialmente en boletines. Si no coinciden, el conector falla. Cada valor de referencia se guarda con la precisión con que se publicó (número de decimales). No se elige ninguna regla de redondeo: el valor pasa si |valor − referencia| ≤ 0,5 × 10^(−precisión). Con precisión 1 la tolerancia es 0,05: 9,36 pasa contra 9,4; 9,30 falla. Con precisión 0 (por ejemplo, el salario mínimo) la tolerancia es 0,5. Cada fuente conserva su propio valor sin redondear. Primeros valores de referencia: inflación anual agosto 2026 = 6,24 %; septiembre 2026 = 6,29 %; año corrido septiembre = 5,74 % (conector del DANE); desempleo julio 2026 = 8,1 %; agosto 2026 = 9,4 %; salario mínimo 2026 = $1.750.905; homicidios intencionales agosto 2026 = 1.190 (Cuadros de salida de la Policía, publicado el 20 oct 2026, provisional). Una diferencia entre versiones provisionales por fecha de corte (por ejemplo, septiembre 2026: 967 en los Cuadros de salida frente a 966 en datos.gov.co) no hace fallar la prueba: se registra como diferencia entre versiones.
5. **Contraste entre fuentes.** Donde dos fuentes publican lo mismo (IPC del DANE y del BanRep), deben coincidir. Donde miden distinto (Policía y MinDefensa), la diferencia se documenta como esperada y no como error. Cada observación guarda su estado de contraste de forma explícita:
   - **aprobado** (`passed`): el contraste se corrió y coincide. Se registra su nivel (por ejemplo, "mensual" o "anual"; un contraste anual no valida la distribución mensual).
   - **pendiente** (`pending`): hay fuente de contraste pero el contraste no se ha corrido. Bloquea. Un contraste que nunca se corrió es siempre "pendiente", nunca "aprobado".
   - **no aplica** (`not_applicable`): la serie tiene una sola fuente oficial (por ejemplo, el salario mínimo). No bloquea.
   - **sin fuente disponible** (`unavailable`): debería haber contraste, pero no existe fuente publicada para ese periodo. No bloquea, pero el motor debe mostrarlo al usuario; si aparece una fuente, el contraste se corre.
   - **no coincide** (`failed`): el contraste se corrió y la diferencia no está registrada. Bloquea. Una diferencia registrada en `known_version_differences` (con el valor exacto de cada fuente) no bloquea; una diferencia nueva, o un cambio en una registrada, va a cuarentena. **IPC y GEIH (DANE frente a SUAMECA):** el DANE es el productor y SUAMECA el canal, así que este contraste mide la coherencia entre publicaciones del mismo dato, no es una verificación independiente. Si una fuente trae menos decimales que la otra, se usa la tolerancia del filtro 4 con la precisión menor: |valor − referencia| ≤ 0,5 × 10^(−precisión menor); es la única regla. **Regla del motor (único lugar donde se define):** el valor del productor se guarda como serie propia (`dane_ipc_annual_national`, `dane_geih_unemployment_rate_national`). El contraste corre en las dos direcciones (`dane_ipc_annual_national` ↔ `inflation_annual_national`, `dane_geih_unemployment_rate_national` ↔ `unemployment_rate_national`): si coinciden, ambas observaciones quedan aprobadas y el motor usa el valor de SUAMECA. Si no coinciden y la diferencia no está registrada, el motor usa el valor del DANE, la observación de SUAMECA queda en cuarentena y **se genera una alerta obligatoria para revisión humana** (un error de lectura de un boletín o de un anexo no debe pasar en silencio). En ambos casos, la radiografía cita al DANE como productor. Los meses que el DANE no cubra quedan "sin fuente disponible". La inflación mensual y la de año corrido vienen solo del DANE y se contrastan con el boletín técnico de cada mes desde 2023 (coherencia dentro del DANE); antes de 2023, "sin fuente disponible". Mientras la fuente de contraste no esté conectada, el dato queda en cuarentena con la marca **"contraste pendiente"** (caso de la inflación y el desempleo hasta que exista el conector del DANE). Si la serie tiene una sola fuente oficial (por ejemplo, el salario mínimo, que fija el decreto), el filtro no aplica y el dato lleva la marca **"sin segunda fuente"**, que no bloquea. Los homicidios de datos.gov.co se contrastan con publicaciones de la Policía: Cuadros de salida (último mes y anual), archivos de delitos a nivel de registro (2020 en adelante) y archivos anuales de la página heredada (2010, 2011, 2013, 2015, 2018 y 2019). **Ese contraste es de consistencia entre publicaciones del mismo sistema (SIEDCO), no una verificación independiente**; la fuente independiente es Medicina Legal (`measured_differently_by` en la ficha). Las fuentes y los años de cada una están en `catalog/sources/homicides_intentional_policia.yaml`. Los archivos originales no van a git (`data/`); en el repositorio quedan solo sus hashes y metadatos (`evidence/`). Como los servidores de la Policía no envían `ETag` ni `Last-Modified`, cada archivo se descarga una vez al mes y se compara su hash. En desarrollo se pueden leer datos en cuarentena, pero solo pidiéndolo de forma explícita.
6. **Vigilancia de cambios.** Si un valor histórico cambia en una nueva descarga: si era provisional, se guarda la nueva versión; si era definitivo, se genera una alerta y se revisa a mano (el IPC es definitivo al publicarse, según la metodología del DANE). Un cambio de base o de marco metodológico (por ejemplo, IPC base diciembre 2018 o GEIH marco 2018) se registra como **serie nueva**, nunca como revisión ni sobrescritura. Cuando la fuente reemplaza una serie histórica (por ejemplo, el empalme de la GEIH de 2022), la cifra publicada en su momento se guarda como otra variante, para explicar diferencias cuando alguien la cite.
7. **Pertinencia en el motor.** Para usar un dato en una radiografía deben coincidir el indicador, la variante, el periodo y el territorio de la afirmación. Si falta alguno, el motor lo dice explícitamente en vez de usar un dato parecido.

### Cuarentena y salud

- Todo dato nuevo entra primero a **cuarentena** y solo pasa a uso cuando supera los filtros 2 a 5. Si falla el filtro 3, sigue en cuarentena hasta que una persona lo revise.
- **Prueba diaria automática** de cada conector: si una API deja de responder o cambia, se avisa y se siguen usando los últimos datos validados, mostrando su fecha de corte.
- **datos.gov.co:** la prueba diaria revisa solo los metadatos del dataset; la descarga completa se hace únicamente cuando cambia `rowsUpdatedAt`. Si pasan más de 45 días sin actualización, se genera una alerta.
- Las pruebas de los filtros 2 a 4 se escriben como pruebas automáticas del repositorio, para que cualquier colaborador del proyecto open source pueda comprobarlas.

### Estado

Los endpoints y formatos están verificados en la documentación oficial; **las llamadas reales a las APIs se comprueban al escribir el primer código**, con los valores de referencia de arriba.

## Migración a Visual Studio Code: pasos y prompt de arranque

### Pasos

1. Exportar este documento en Markdown y guardarlo en el repositorio como `docs/PROYECTO.md`. Es la fuente única de verdad.
2. Crear en la raíz del repositorio un archivo `CLAUDE.md` con el prompt de abajo. Claude Code lo lee automáticamente al empezar cada sesión; con otro asistente, pegarlo como primer mensaje.
3. Cada vez que se cierre una decisión, actualizar `docs/PROYECTO.md` (checklist y backlog) en el mismo commit.

### Prompt de arranque (contenido de `CLAUDE.md`)

```
Eres colaborador de un proyecto open source: una plataforma colombiana que muestra
los datos oficiales completos detrás de afirmaciones públicas, para que nadie, de
ningún lado político, consuma medias verdades o información sin contexto.

ANTES DE HACER CUALQUIER COSA lee docs/PROYECTO.md. La sección "Brief del proyecto"
manda sobre todo lo demás. Las secciones marcadas como contexto histórico
(despolarización) NO son objetivos.

Reglas que no se negocian:
- No buscamos cambiar opiniones ni despolarizar. Misma vara para todos.
- No decimos verdadero/falso: la conclusión se sostiene, se debilita o se invierte.
- Ningún número sale si no viene de una fuente oficial registrada y verificada
  (protocolo de siete filtros en docs/PROYECTO.md). Si no hay dato comparable,
  se dice; nunca se aproxima.
- Lo que la fuente oficial publica no se calcula. Un cálculo solo se permite si
  la fuente no publica ese valor, y se guarda y se muestra como "cálculo propio"
  con su fórmula y las series usadas.
- Alcance v1 cerrado: 4 funcionalidades y 8 indicadores. Las ideas nuevas van
  al backlog, no al código.
- Primero funcionalidad y bases de datos; la parte visual va al final.
- Mientras sea proyecto de la materia: código en español sin tildes según `docs/diseno/glosario_codigo.md` (decisión 14); los conectores existentes y los códigos del catálogo siguen en inglés. Textos al usuario en español.
- Lenguaje neutral: describir lo que pasa con el dato, nunca la intención de
  quien lo dijo (pendiente: glosario oficial al crear el repositorio).

Stack: Python + FastAPI, PostgreSQL + pgvector. Cada base de datos detrás de su
propia interfaz para poder sumar o quitar motores.

Paso actual: construir los dos primeros conectores (Banco de la República vía
la API JSON de SUAMECA y datos SIEDCO vía API Socrata de datos.gov.co), con
pruebas automáticas que comparen contra los valores de referencia del documento. Después: modelo de
datos en PostgreSQL y carga del conjunto de prueba de 30 afirmaciones.

Antes de escribir código grande, propón un plan corto y espera confirmación.
Si algo del documento es ambiguo, pregunta en vez de suponer.
```

## Definición del producto v1 (alcance cerrado, 25 oct 2026)

Enfoque acordado: la plataforma no busca cambiar opiniones ni despolarizar. Busca que cualquier persona, de cualquier lado, vea los datos completos detrás de lo que le dicen. Las secciones posteriores sobre despolarización quedan como contexto, no como objetivo.

Regla de trabajo: primero funcionalidad y bases de datos al 100 %; la parte visual va después, en su propia fase.

| Funcionalidad | Qué hace | Factibilidad y evidencia | Fuera de alcance v1 | Terminada cuando… |
| --- | --- | --- | --- | --- |
| 1. Radiografía de una noticia (compartir desde cualquier app + bot de WhatsApp) | Recibe enlace, texto o captura; separa dato, interpretación y opinión; aplica pruebas de robustez (inflación, per cápita, periodo, base); dice si la conclusión se sostiene, se debilita o se invierte | Alta en lo técnico. Demanda comprobada: una línea de WhatsApp en India recibió 157.995 mensajes en 4 meses, 82.676 únicos ([HKS Misinformation Review](https://misinforeview.hks.harvard.edu/article/research-note-tiplines-to-uncover-misinformation-on-encrypted-platforms-a-case-study-of-the-2019-indian-general-election-on-whatsapp/), [arXiv 2106.04726](https://arxiv.org/html/2106.04726)). Límite: verificar cifras automáticamente sigue siendo difícil para la IA ([CheckThat! CLEF 2026](https://arxiv.org/html/2607.25069v1)); las medias verdades son lo más difícil de detectar ([Wang et al. 2025](https://journals.sagepub.com/doi/10.1177/19462174251330980)) | Video, deepfakes, afirmaciones sin datos medibles | Analiza correctamente un conjunto de prueba de afirmaciones reales en un dominio (ej. economía), sin cifras inventadas, y responde por app y WhatsApp |
| 2. Temas de la semana (7 automáticos + 3 sugeridos por la comunidad) | Detecta los temas más difundidos; recoge declaraciones de todos los actores; contrasta con datos oficiales; muestra confusiones y lo que nadie menciona. Buzón de sugerencias agrupadas por similitud, con peso a apoyos diversos | Alta. Agrupar sugerencias por similitud es barato y escala. Riesgo: presión organizada para imponer temas; se mitiga con pesos por diversidad y límites a cuentas nuevas | Ciclo diario; cobertura regional | Publica 10 temas semanales durante 4 semanas seguidas con fuentes verificables en cada cifra |
| 3. Archivo de declaraciones y promesas | Perfil por figura pública con lo dicho y prometido, contrastado en el tiempo con datos y con sus declaraciones previas | Media. Precedentes sólidos: PolitiFact califica promesas por resultados verificables, no intenciones ([PolitiFact](https://politifact.com/truth-o-meter/promises/biden-promise-tracker/)). Riesgo: volumen de trabajo; los propios equipos advierten que con demasiadas promesas se vuelve inmanejable ([Journalism Studies 2025](https://www.tandfonline.com/doi/full/10.1080/1461670X.2025.2477001)); riesgo legal | Más de 10–15 figuras; ciudadanos privados | Archivo completo para un grupo pequeño de figuras (ej. presidente y gabinete) con estados claros y fuentes |
| 4. Opiniones y debate anclados a temas y radiografías | Comentar, compartir opinión y debatir dentro de cada tema o análisis; las cifras en comentarios se etiquetan; se destacan aportes con evidencia | Media-baja por adopción y moderación, no por tecnología. Por eso v1 no tiene feed abierto | Feed social libre (fase posterior) | Usuarios pueden opinar y debatir en cada tema con etiquetado automático de cifras y moderación básica |

**Para el proyecto de I+D de bases de datos** (sin enunciado aún), el diseño se deja abierto así:

- **Transaccional (PostgreSQL):** usuarios, radiografías, temas, sugerencias, comentarios, votos. Núcleo obligatorio.
- **Vectorial (pgvector):** detectar noticias que dicen lo mismo y agrupar sugerencias de temas. Encaja con las funcionalidades 1 y 2.
- **Opcionales según el enunciado:** grafos (quién sigue a quién, cómo se difunde una noticia), series de tiempo (datos oficiales), caché (feed y tendencias).
- Recomendación: mantener las bases como módulos con interfaces claras, para sumar o quitar motores cuando llegue el enunciado sin rehacer la app.

### Catálogo de fuentes v1: 8 indicadores (Colombia)

Cada indicador tiene una fuente principal (la que usa el motor) y fuentes de contraste (para detectar cuando alguien cita la que le conviene).

| Indicador | Fuente principal | Contraste | Frecuencia | Trampas típicas a detectar |
| --- | --- | --- | --- | --- |
| Inflación | DANE, IPC base 2018 ([DANE IPC](https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc)) | Banco de la República | Mensual | Mezclar variación mensual, año corrido y anual (ej. agosto 2026: 0,39 %, 5,35 % y 6,24 %, [DANE](https://www.dane.gov.co/)); hablar de "baja de precios" cuando solo baja la inflación |
| Desempleo | DANE, GEIH ([DANE GEIH](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo)) | Series empalmadas del Banco de la República ([BanRep](https://www.banrep.gov.co/economia/pli/bie.pdf)) | Mensual | Comparar meses distintos (estacionalidad: julio 2026 8,1 % vs agosto 9,4 %); ignorar la tasa de participación; usar series sin empalme de 2022 |
| Salario mínimo | Decreto anual del Gobierno | Ajuste contra inflación del DANE | Anual | Hablar del aumento nominal sin descontar inflación |
| Deuda pública | MinHacienda, deuda del Gobierno Nacional Central ([MinHacienda](https://www.minhacienda.gov.co/deuda-publica), [IRC](https://www.irc.gov.co/en/public-debt/gnc-public-debt-profile)) | Banco de la República ([BanRep](https://www.banrep.gov.co/es/estadisticas/deuda-publica)) | Mensual | Pesos vs % del PIB; deuda bruta vs neta; externa vs total; entidades miden distinto ([Contaduría](https://www.contaduria.gov.co/documents/20127/6058789/Comparaci%C3%B3n+y+an%C3%A1lisis+de+la+medici%C3%B3n+de+la+deuda+p%C3%BAblica+del+Gobierno+Nacional+Central.pdf/780d0a42-d537-31cd-ec05-5cf43d0a56d3?version=1.0&t=1693919923288&download=true)) |
| Homicidios | Policía Nacional, SIEDCO ([Policía](https://www.policia.gov.co/estadistica-delictiva)) | Medicina Legal; tasa por 100.000 hab. de MinJusticia ([MinJusticia](https://www.minjusticia.gov.co/programas-co/politica-criminal/Paginas/SIPC-Tasa-de-Homicidios-Basada-en-reporte-de-homicidios-de-la-Policia-Nacional.aspx)) | Mensual | Elegir la fuente conveniente; números absolutos sin tasa; datos provisionales (solo son definitivos en marzo del año siguiente) |
| Hurtos | Policía Nacional, SIEDCO | DANE, Encuesta de Convivencia y Seguridad Ciudadana (subregistro) | Mensual / anual | Confundir denuncias con delitos; mezclar modalidades (personas, residencias, comercio) |
| Extorsión | Policía Nacional, SIEDCO; Ministerio de Defensa ([MinDefensa](https://www.mindefensa.gov.co/defensa-y-seguridad/datos-y-cifras/informacion-estadistica)) | DANE, encuesta de convivencia | Mensual | Bajas en denuncias leídas como bajas en delito; periodos cortos |
| Secuestro | Ministerio de Defensa | Policía Nacional, SIEDCO | Mensual | Porcentajes sobre bases pequeñas; comparar un solo mes |

**Primer caso de prueba ya identificado:** tras el primer mes del nuevo gobierno se reportaron caídas de 25 % en secuestro, 46 % en denuncias de extorsión y 49 % en hurto a personas ([El País](https://www.elpais.com.co/colombia/mindefensa-presenta-cifras-de-orden-publico-durante-primer-mes-del-gobierno-de-abelardo-de-la-espriella-hubo-mas-de-14000-capturas-0845.html)), y en otro reporte, 79 % en secuestro frente a agosto de 2025 ([CRprensa](https://crprensa.com/2026/09/30/gobierno-de-colombia-reporta-importantes-reducciones-en-secuestros-extorsiones-y-masacres/)). El motor debería revisar: periodo de un mes, base de comparación, denuncias vs delitos y datos provisionales. Esto no dice que las cifras sean falsas; dice qué hay que mirar para entenderlas.

Pendiente: confirmar en cada portal el formato de descarga (Excel, API o datos.gov.co) antes de construir los conectores.

Oct 21, 2026 · @Dubal

## Mi opinión en corto

La idea es buena y el diagnóstico es correcto: el problema principal no es la noticia falsa, sino el dato real usado sin contexto. Pero tal como está planteada, corre el riesgo de construir un muy buen verificador que nadie polarizado usa ni cree.

**Lo más fuerte de la propuesta:**

- Calificar la *cobertura del dato* en vez de decir "miente / no miente". Esto esquiva el formato que la evidencia muestra menos eficaz (las escalas de verdad).
- El enfoque en coyuntura (los 10 temas del día) en vez de verificar post por post.
- La combinación de IA con validación por *bridging*, que hoy es lo más sólido que existe para ganar credibilidad entre bandos.

**Los tres cambios que yo haría:**

1. **Atacar la polarización afectiva, no solo la factual.** En Colombia la división es de miedo y rechazo al otro, no solo de datos. Corregir datos no baja ese rechazo; corregir lo que la gente cree *del otro bando* sí lo baja.
2. **Ir donde ya está la gente: WhatsApp y video corto.** Una red social nueva compite contra TikTok y Facebook. Un servicio que vive dentro de WhatsApp, más una web, tiene mucha más probabilidad de uso.
3. **Hacer de la neutralidad un proceso verificable, no una promesa.** Nadie va a creer que una IA es 100 % neutral. Sí pueden creer un proceso abierto, auditable y validado por personas de ambos lados.

El resto del documento sustenta estas tres ideas con datos y las baja a producto, tecnología y hoja de ruta.

## Contexto actual: un país partido por la mitad que desconfía de todos

Colombia sale de 2026 con una división casi exacta: Abelardo de la Espriella ganó la segunda vuelta del 21 de junio con 12.960.166 votos frente a 12.708.312 de Iván Cepeda, una diferencia de unos 252.000 votos (≈50,5 % vs 49,5 %). El resultado fue impugnado y solo se aceptó tras un escrutinio de tres días ([Telemundo](https://www.telemundo51.com/noticias/mundo/termina-el-escrutinio-abelardo-de-la-espriella-es-el-presidente-electo-de-colombia/2797070/?amp=1)). Ese es justo el terreno donde una plataforma de contexto puede servir, y también donde cualquier error de neutralidad se paga caro.

| Indicador | Dato | Por qué importa al proyecto |
| --- | --- | --- |
| Concentración del voto en primera vuelta | Los dos finalistas sumaron más del 84 %; voto en blanco 1,71 % ([Publimetro](https://www.publimetro.co/bogota/2026/06/01/informe-revela-una-colombia-polarizada-de-la-espriella-y-cepeda-concentraron-mas-del-84-de-los-votos-en-primera-vuelta/)) | El centro político colapsó: tu público "neutral" es pequeño. Hay que diseñar para gente que ya tiene bando. |
| Confianza en las noticias | Cayó de 32 % a 25 %; Colombia es de los países con menor confianza en LatAm ([Reuters Institute DNR 2026](https://reutersinstitute.politics.ox.ac.uk/es/digital-news-report/2026)) | Una marca nueva parte desde la desconfianza. La credibilidad hay que construirla con método, no con discurso. |
| Quiénes más desconfían | Los más interesados en política son los que más desconfían de las noticias ([Vanguardia, sobre DNR 2026](https://www.vanguardia.com/entretenimiento/tendencias/2026/07/28/estudio-revela-que-tendencia-politica-consume-mas-noticias-de-influencers-y-creadores-en-colombia/)) | Tu usuario más activo será también el más escéptico. |
| Noticias por creadores/influencers | 35 % de colombianos se informa así ([Reuters Institute DNR 2026](https://reutersinstitute.politics.ox.ac.uk/es/digital-news-report/2026)) | La conversación no está en los medios; está en personas. Hay que auditar también a creadores. |
| Canales de noticias | 76 % se informa en línea y 58 % por redes sociales; Facebook, WhatsApp y YouTube lideran ([IDEA Internacional](https://www.idea.int/publications/catalogue/html/desinformacion-electoral-en-colombia), [Radio Nacional sobre DNR 2025](https://radionacional.co/actualidad/rtvc-noticias-segundo-medio-mas-confiable-segun-digital-news-report-2025)) | Una red social nueva compite contra hábitos muy fuertes. WhatsApp es canal, no rival. |
| Campañas de desinformación | La MOE identificó 150 campañas entre marzo 2025 y marzo 2026 ([El Tiempo](https://www.eltiempo.com/politica/elecciones-colombia-2026/los-ingredientes-que-cambiaron-la-forma-de-hacer-campana-a-la-presidencia-3565785)) | Hay volumen suficiente para justificar un "radar" diario. |
| Exposición percibida | 78 % dice haber visto desinformación el último año ([Publimetro, estudio Kaspersky](https://www.publimetro.co/tecnologia/2026/05/26/cuidado-al-dar-sus-datos-para-las-elecciones-alertan-hackeos-y-robos-a-una-semana-de-las-votaciones/)) | Hay demanda declarada; el reto es que se convierta en uso. |
| Confianza en la IA para informarse | Crece su uso, pero la confianza es baja, incluso menor que en redes ([Cambio, sobre DNR 2026](https://cambiocolombia.com/pais/articulo/2026/7/que-tanto-confian-los-colombianos-en-la-ia-para-informarse-esto-revelo-un-estudio)) | Vender el producto como "IA neutral" juega en contra. La IA debe ser el motor, no la promesa. |

Tres rasgos del ecosistema son clave para el diseño:

- **La polarización es afectiva.** Análisis de La Silla Vacía muestran que el candidato puntero era a la vez el más rechazado: se vota por miedo al otro, no solo por afinidad ([La Silla Vacía](https://www.lasillavacia.com/?p=389083)).
- **La campaña cambió de escenario.** Hubo redes coordinadas de influenciadores, *streamings* masivos, IA y ausencia de debates ([El Tiempo](https://www.eltiempo.com/politica/elecciones-colombia-2026/los-ingredientes-que-cambiaron-la-forma-de-hacer-campana-a-la-presidencia-3565785)). MinTIC reportó patrones de distribución coordinada para amplificar narrativas ([El Universal](https://www.eluniversal.com.co/colombia/2026/06/16/mintic-alerta-sobre-operaciones-de-interferencia-y-desinformacion-de-cara-a-elecciones/)).
- **En Colombia la desinformación tiene costo físico.** Con violencia política y control territorial de grupos armados ([IDEA Internacional](https://www.idea.int/publications/catalogue/html/desinformacion-electoral-en-colombia)), un error de la plataforma puede exponer a personas. Esto pesa en el diseño de seguridad (sección de riesgos).

## Qué dice la evidencia: corregir datos ayuda, pero no despolariza

La investigación converge en una idea incómoda para el proyecto: verificar funciona en promedio, pero su efecto es pequeño frente a la identidad política, y no reduce el odio entre bandos. Lo que sí reduce ese odio es otro tipo de intervención.

| Hallazgo | Evidencia | Implicación para el diseño |
| --- | --- | --- |
| El fact-checking corrige, con efecto moderado | Meta-análisis de 30 estudios (≈21.000 personas): efecto positivo d = 0,29; se debilita con "escalas de verdad", con refutaciones parciales y en temas de campaña ([Walter et al., Political Communication 2020](https://cris.haifa.ac.il/en/publications/fact-checking-a-meta-analysis-of-what-works-and-for-whom/)) | Tu idea de calificar la *cobertura del dato* en vez de un semáforo de verdad va en la dirección correcta. Evita el "60 % sesgado" si suena a nota moral. |
| La identidad pesa más que el dato | El efecto de la congruencia partidista fue 5 veces mayor que el de la corrección; las correcciones del grupo rival tenían 52 % más probabilidad de "rebotar" ([Nieman Lab](https://www.niemanlab.org/2023/06/when-it-comes-to-misinformation-partisanship-overpowers-fact-checking-over-and-over-again/)) | Quién firma la corrección importa tanto como el contenido. De ahí el valor del *bridging*: que la valide gente de ambos lados. |
| El "efecto rebote" general es raro | Wood y Porter no encontraron rebote en temas muy polarizados ([OUP blog](https://educationblog.oup.com/theory-of-knowledge/facts-matter-after-all-rejecting-the-backfire-effect)) | Corregir vale la pena. Somos resistentes a los hechos, no inmunes. |
| Corregir no reduce la polarización | Un estudio citado por el DFRLab halló que la desinformación genera polarización que persiste aunque se corrija el dato ([DFRLab](https://dfrlab.org/2020/06/23/hearts-and-minds-misinformation-polarization-and-resistance-to-fact-checking/)) | Si la meta es "partir la polarización", la verificación sola no basta. Hace falta un segundo motor. |
| Corregir percepciones del *otro* sí despolariza | Megaestudio de Stanford (32.059 personas, 25 intervenciones): 23 redujeron la animosidad; las más fuertes mostraban personas cercanas del otro bando, identidades compartidas y corrección de percepciones erróneas sobre el rival ([Stanford Sociology](https://sociology.stanford.edu/scalable-interventions-reduce-polarization-support-partisan-violence-and-anti-democratic-attitudes)) | Este es el segundo motor: auditar también lo que creemos que *piensa el otro bando*. |
| Bajar el odio no arregla todo | Reducir la animosidad no cambió automáticamente las actitudes antidemocráticas ([Northwestern](https://news.northwestern.edu/stories/2022/10/partisans-willing-to-upend-democracy-to-help-their-party-win-even-when-polarization-is-diminished)) | Mide por separado: creencias erróneas, animosidad y compromiso democrático. |
| La IA conversacional puede cambiar creencias | Diálogos personalizados con GPT-4 redujeron creencias conspirativas \~20 %, con efecto a los 2 meses, incluso en creyentes fuertes, y sin reducir la creencia en conspiraciones verdaderas ([Costello, Pennycook y Rand, Science 2024](https://mitsloan.mit.edu/node/48296)) | El "Inspector" no debería ser solo una ficha estática: un diálogo que responde a *los argumentos del usuario* es mucho más potente. |

**Lo que enseña Community Notes (el modelo que quieres adaptar):**

- Funciona en calidad: en vacunas, más del 97 % de las notas fueron precisas ([arXiv 2410.12699](https://arxiv.org/pdf/2410.12699)).
- Falla en cobertura y velocidad: solo cerca del 10 % de las notas se publica ([arXiv 2512.19947](https://arxiv.org/pdf/2512.19947)), y un estudio halló que 74 % de los posts engañosos con nota precisa nunca la mostraron ([arXiv 2511.02615](https://arxiv.org/pdf/2511.02615)).
- Es manipulable: es muy sensible al sesgo de los evaluadores ([arXiv 2511.02615](https://arxiv.org/pdf/2511.02615)) y mide la división en un solo eje, que puede no funcionar igual entre idiomas ([arXiv 2609.21496](https://arxiv.org/pdf/2609.21496)).
- Se desgasta: cuando las notas no se publican, los autores abandonan ([arXiv 2510.00650](https://arxiv.org/pdf/2510.00650)).
- Ya se mezcla con IA: X introdujo notas redactadas por un LLM y refinadas por humanos ([arXiv 2606.30905](https://arxiv.org/pdf/2606.30905)). Tu arquitectura (IA propone, comunidad valida) ya tiene precedente y se puede estudiar.

## Mejoras desde lo social

Mi propuesta central: que la plataforma tenga **dos motores**. El que ya diseñaste (auditar el dato) y uno nuevo (auditar lo que creemos del otro bando). El segundo es el que la evidencia asocia con bajar la polarización.

1. **Agregar un "Termómetro de percepciones" (el segundo motor).**
   - Cada semana, encuestar a usuarios de ambos lados sobre un tema ("¿qué % de votantes de X cree que…?") y mostrar la brecha entre lo que la gente *cree* que piensa el otro y lo que *de verdad* piensa.
   - Corregir percepciones del rival es de las intervenciones más efectivas del megaestudio de Stanford, y More in Common la ha replicado con buenos resultados ([Stanford](https://news.stanford.edu/stories/2022/08/how-to-strengthen-democracy), [More in Common](https://www.moreincommon.com/media/gqxcdxfb/mic_overcoming-distrust-experiment_report.pdf)).
   - Es contenido original y compartible que ningún medio colombiano produce de forma sistemática.
2. **Mostrar "en qué estamos de acuerdo" en cada tema del Radar.**
   - Usar una dinámica tipo Polis: la gente vota afirmaciones cortas y el sistema destaca las que tienen apoyo en *ambos* grupos ([ICIP](https://www.icip.cat/perlapau/en/article/bridging-algorithms-as-practical-tools-for-depolarisation/)).
   - Polis se ha usado en vTaiwan y en decenas de países; no tiene botón de respuesta, lo que reduce el troleo ([Long-term Wiki](https://www.longtermwiki.com/wiki/E2718)).
   - En Colombia, mostrar que una mayoría de ambos bandos coincide en algo (por ejemplo, en seguridad rural o empleo) es un mensaje despolarizador en sí mismo.
3. **Cambiar el tono de la calificación.** Un "60 % datos sesgados" se lee como acusación y activa la defensa de identidad. Mejor una ficha descriptiva: *qué dijo · qué dato usó · qué dato faltaba · cómo cambia la lectura con el dato completo*. Las escalas de verdad debilitan el efecto de la verificación ([Walter et al.](https://cris.haifa.ac.il/en/publications/fact-checking-a-meta-analysis-of-what-works-and-for-whom/)).
4. **Simetría visible y contable.** Publica cada mes cuántas fichas se hicieron sobre afirmaciones de cada sector político, y con qué resultado. Si el gobierno de turno es de derecha, habrá más fichas sobre él por volumen de poder; explícalo con datos antes de que te acusen. La neutralidad se demuestra con contabilidad, no con adjetivos.
5. **Mensajeros de ambos lados.** Como las correcciones del grupo rival rebotan más ([Nieman Lab](https://www.niemanlab.org/2023/06/when-it-comes-to-misinformation-partisanship-overpowers-fact-checking-over-and-over-again/)), cada ficha importante debería poder mostrar "validada por revisores que votaron distinto". Mejor aún: un consejo editorial público con perfiles reconocidos de ambos bloques.
6. **Distribución dentro de WhatsApp, TikTok y Facebook.** No obligues a la gente a migrar.
   - Un bot de WhatsApp donde reenvías un mensaje y recibes la ficha. Chequeado y Colombiacheck ya tienen experiencia con este formato ([Chequeado](https://chequeado.com/?p=32183)).
   - Fichas en formato imagen/video corto, diseñadas para reenviarse a grupos familiares. El 74 % de los verificadores dice que el video corto es el formato que mejor llega a públicos nuevos ([Poynter/IFCN](https://poynter.org/?p=1153978)).
   - La "red social" propia puede venir después, cuando haya comunidad.
7. **Auditar creadores, no solo medios.** Con 35 % de colombianos informándose por influencers ([Reuters Institute](https://reutersinstitute.politics.ox.ac.uk/es/digital-news-report/2026)), el Radar debe incluir afirmaciones de *streamers* y creadores, con el mismo criterio.
8. **Alfabetización integrada, no aparte.** Cada ficha puede enseñar *un* truco ("cuidado con el eje Y que no empieza en cero", "esta cifra no está ajustada por inflación"). Con el tiempo, el usuario aprende a detectarlo solo.
9. **Enfoque regional.** La votación se partió por regiones (por ejemplo, Bucaramanga vs Santa Marta, [El Tiempo](https://www.eltiempo.com/politica/elecciones-colombia-2026/como-votaron-bogota-medellin-y-otras-ciudades-en-colombia-asi-les-fue-a-abelardo-de-la-espriella-e-ivan-cepeda-en-la-segunda-vuelta-presidencial-3566040)). Datos departamentales del DANE hacen el contexto más cercano y menos "bogotano".

## Mejoras desde lo tecnológico

Tu arquitectura base (detección de afirmaciones, RAG con fuentes oficiales, agentes adversariales) es sólida. Le sumaría cinco piezas que la hacen más creíble, más barata y más difícil de manipular.

&#91;embedded content: arquitectura propuesta · 3 entradas, 5 etapas, 3 salidas\]

La IA prepara; las personas de bandos distintos deciden qué se publica; todo queda registrado.

1. **Verificador de citas obligatorio.** El mayor riesgo de un LLM aquí es inventar o redondear una cifra. Toda cifra de la ficha debe enlazar a la serie oficial exacta (tabla, fecha de corte, unidad). Si no coincide, la ficha no avanza. Esto es más importante que la neutralidad del modelo.
2. **Diversidad real de modelos, no solo de prompts.** Que el Agente A, el Agente B y el sintetizador sean de proveedores distintos (por ejemplo, un modelo abierto tipo Llama o Mistral y uno comercial). Así el sesgo de un proveedor no domina todo el flujo. Mide el sesgo con pruebas espejo: la misma afirmación atribuida a un político de izquierda y a uno de derecha debe recibir la misma ficha.
3. **Bridging mejorado frente a los fallos de Community Notes.**
   - Usa el algoritmo abierto de X como base, pero con más de un eje de desacuerdo: en Colombia la división no es solo izquierda–derecha, también es regional y urbano–rural ([arXiv 2609.21496](https://arxiv.org/pdf/2609.21496)).
   - Que la IA redacte el borrador y los humanos solo voten, para ganar velocidad y no desgastar a los autores ([arXiv 2606.30905](https://arxiv.org/pdf/2606.30905), [arXiv 2510.00650](https://arxiv.org/pdf/2510.00650)).
   - Defensas contra manipulación: reputación por historial, detección de votos coordinados y verificación de identidad ligera (una cuenta = una persona) ([arXiv 2511.02615](https://arxiv.org/pdf/2511.02615)).
4. **El Inspector como diálogo, no como formulario.** En vez de solo devolver una ficha, que pueda conversar con el usuario y responder *sus* argumentos con datos. Es el formato que mostró un efecto de \~20 % y duradero en el estudio de Science ([MIT Sloan](https://mitsloan.mit.edu/node/48296)). Con reglas estrictas: no persuadir sobre opiniones o candidatos, solo sobre hechos verificables.
5. **Verificación de medios sintéticos.** Con deepfakes y audios falsos en la campaña ([Portafolio](https://www.portafolio.co/economia/gobierno/deepfakes-y-elecciones-2026-crece-la-alerta-por-contenido-falso-en-redes-sociales-durante-la-carrera-presidencial-494957)), el Inspector debe revisar credenciales de contenido (estándar C2PA) cuando existan y usar detectores externos, pero comunicando la incertidumbre: los detectores fallan y una falsa acusación de "deepfake" también desinforma.
6. **Detección de campañas coordinadas.** El Radar puede mostrar no solo *qué* se dice, sino *cómo se mueve*: picos simultáneos, cuentas nuevas, textos idénticos. MinTIC y la MOE describieron este patrón en 2026 ([El Universal](https://www.eluniversal.com.co/colombia/2026/06/16/mintic-alerta-sobre-operaciones-de-interferencia-y-desinformacion-de-cara-a-elecciones/)). Esto es útil para periodistas y difícil de tachar de partidista.
7. **Stack.** Mantengo lo que planteaste (FastAPI, PostgreSQL + pgvector, LangChain o LlamaIndex) y agrego: un repositorio de "series oficiales" versionado (cada dato con fecha de corte), la API de WhatsApp Business para el bot, y un registro público de cada ficha (prompts, modelos, fuentes y votos). Ese registro es tu mejor argumento de neutralidad.

## Riesgos legales, de gobernanza y sostenibilidad

El riesgo más grande no es técnico: es que la plataforma sea capturada (por un bando, un financiador o un ataque coordinado) o que se quede sin dinero.

| Riesgo | Contexto real | Mitigación |
| --- | --- | --- |
| Financiación frágil | Tres cuartas partes de los verificadores encuestados por la IFCN dicen estar en situación vulnerable o de crisis; en 2025 cerraron tres veces más proyectos de los que abrieron ([Duke Reporters' Lab](https://reporterslab.org/?p=4294)) | No depender de una sola fuente. Mezclar: fundaciones, membresías ciudadanas, licencias del Radar y la API a medios, universidades y ONG, y servicios B2B (monitoreo para empresas o entidades). Publicar quién financia y cuánto. |
| Meta reemplaza verificadores en LatAm | En septiembre 2026 Meta empezó a probar Community Notes en 16 países hispanohablantes de la región, con miras a sustituir su programa de verificación ([Buenos Aires Times](https://batimes.com.ar/news/culture/meta-tests-fact-check-replacement-in-latin-america.phtml)) | Es amenaza y oportunidad: habrá verificadores y comunidades buscando nueva infraestructura. Ofrécete como herramienta para ellos, no como competidor. |
| Acusación de sesgo | Con un país 50/50, cualquier ficha será leída como ataque por la mitad del público | Simetría contable publicada mensualmente, consejo plural, registro abierto, auditoría externa anual, y adherir al código de la IFCN. |
| Regulación de IA en curso | Colombia discute un proyecto de ley de IA con clasificación por niveles de riesgo y supervisión humana ([OCDE](https://oecd.ai/en/dashboards/policy-initiatives/artificial-intelligence-bill-in-colombia)); hay nuevos proyectos radicados en julio 2026 ([Gaceta del Congreso 878](https://www.redjurista.com/Compilaciones2018/gacetasCongreso/2026/gc_0878_2026.pdf)) | Diseñar desde ya con supervisión humana, explicabilidad y registro: es lo que estas leyes piden. Seguir el trámite con un abogado. |
| Datos personales | La Ley 1581 (habeas data) protege datos de opinión política como sensibles; además se discute su actualización ([Impacto TIC](https://impactotic.co/innovacion/elecciones-2026-colombia-la-agenda-tic-que-definira-al-pais/)) | El "Monitor de sesgos" personal debe ser opcional, procesado en el dispositivo cuando se pueda, sin vender ni cruzar datos. Pide asesoría legal antes de guardar la inclinación política de nadie. |
| Seguridad física | En Colombia la desinformación puede derivar en violencia ([Semana](https://www.semana.com/mejor-colombia/elecciones/articulo/que-tanto-influyen-las-redes-sociales-en-la-opinion-politica-de-los-colombianos-estos-son-los-riesgos-que-ha-detectado-la-registraduria/202631/)); el acoso a verificadores es una amenaza constante ([Poynter](https://poynter.org/?p=1153978)) | Anonimato de revisores, no auditar a ciudadanos privados (solo figuras públicas y cuentas de alcance masivo), protocolo para temas de orden público y personas en riesgo. |
| Captura del algoritmo | Community Notes es sensible al sesgo de evaluadores y a la manipulación ([arXiv 2511.02615](https://arxiv.org/pdf/2511.02615)) | Defensas de la sección tecnológica, más una regla: ningún financiador ni socio tiene voz sobre fichas concretas. |

**Gobernanza que sugiero:** una fundación sin ánimo de lucro dueña del método y del registro, con un consejo plural (academia, ambos bloques políticos, verificadores); y, si se quiere escalar, una empresa social separada que venda servicios. Así la marca de neutralidad no depende del modelo de negocio.

## Hoja de ruta replanteada y métricas de impacto

Propongo empezar pequeño y en un solo tema, para llegar con un método probado a las elecciones regionales de octubre de 2027 (gobernaciones y alcaldías).

1. **Fase 0 — Método y alianzas (1–2 meses).**
   - Escribir el manual de la ficha (qué es "dato completo", qué omisiones se marcan) y probarlo a mano con 30 afirmaciones reales.
   - Conversar con Colombiacheck, La Silla Vacía (que ya experimenta con su chatbot SillaIA, según el [Reuters Institute](https://reutersinstitute.politics.ox.ac.uk/es/digital-news-report/2026/colombia)), la MOE y alguna universidad. Mejor socio que competidor.
   - Convocar a 20–40 revisores de perfiles políticos distintos.
2. **Fase 1 — MVP del Inspector + bot de WhatsApp (2–3 meses).** Un solo dominio con buenos datos oficiales: economía (inflación, empleo, deuda) o seguridad. Fichas con verificador de citas y validación humana.
3. **Fase 2 — Radar semanal + Termómetro de percepciones (3 meses).** Un boletín semanal con 5 temas, más una encuesta de percepciones cruzadas por mes. Publicar la primera "contabilidad de simetría".
4. **Fase 3 — Bridging abierto y diálogo con evidencia (3–6 meses).** Abrir la votación a más usuarios, activar el Inspector conversacional y el detector de campañas coordinadas.
5. **Fase 4 — Elecciones regionales 2027 y expansión.** Cobertura por departamento. Luego, adaptar el método a otro país de la región.

**Cómo medir si de verdad tiene impacto** (mide tres cosas por separado, porque bajar una no garantiza bajar las otras):

| Qué se mide | Cómo | Meta orientativa |
| --- | --- | --- |
| Creencias erróneas | Encuesta antes y después de ver la ficha, con grupo de control | Reducción medible en ambos bandos, no solo en uno |
| Polarización afectiva | "Termómetro de sentimientos" hacia el otro bando, antes y después | Reducción sostenida a 2–4 semanas |
| Confianza cruzada | % de usuarios de cada bando que califica la plataforma como justa | Diferencia entre bandos menor a 10 puntos |
| Alcance real | Reenvíos de fichas en WhatsApp y redes, consultas al bot | Crecimiento mes a mes |
| Calidad | Errores corregidos por cada 100 fichas, tiempo de publicación | Errores cerca de cero; publicación en horas, no días |

La métrica que más importa es la confianza cruzada: si una mitad del país te considera justa y la otra no, la plataforma no está despolarizando, aunque los datos sean impecables. Una alianza con una universidad para hacer esta evaluación con rigor también abre puertas a financiación.

## Fuentes

**Contexto colombiano**

- [Telemundo — Escrutinio: De la Espriella presidente electo](https://www.telemundo51.com/noticias/mundo/termina-el-escrutinio-abelardo-de-la-espriella-es-el-presidente-electo-de-colombia/2797070/?amp=1)
- [Publimetro — Concentración del voto en primera vuelta](https://www.publimetro.co/bogota/2026/06/01/informe-revela-una-colombia-polarizada-de-la-espriella-y-cepeda-concentraron-mas-del-84-de-los-votos-en-primera-vuelta/)
- [El Tiempo — Cómo cambió la campaña 2026](https://www.eltiempo.com/politica/elecciones-colombia-2026/los-ingredientes-que-cambiaron-la-forma-de-hacer-campana-a-la-presidencia-3565785)
- [El Tiempo — Votación por ciudades](https://www.eltiempo.com/politica/elecciones-colombia-2026/como-votaron-bogota-medellin-y-otras-ciudades-en-colombia-asi-les-fue-a-abelardo-de-la-espriella-e-ivan-cepeda-en-la-segunda-vuelta-presidencial-3566040)
- [La Silla Vacía — Polarización afectiva](https://www.lasillavacia.com/?p=389083)
- [IDEA Internacional — Desinformación electoral en Colombia (mayo 2026)](https://www.idea.int/publications/catalogue/html/desinformacion-electoral-en-colombia)
- [El Universal — Alerta de MinTIC](https://www.eluniversal.com.co/colombia/2026/06/16/mintic-alerta-sobre-operaciones-de-interferencia-y-desinformacion-de-cara-a-elecciones/)
- [Portafolio — Deepfakes y elecciones](https://www.portafolio.co/economia/gobierno/deepfakes-y-elecciones-2026-crece-la-alerta-por-contenido-falso-en-redes-sociales-durante-la-carrera-presidencial-494957)
- [Semana — Redes sociales y opinión política](https://www.semana.com/mejor-colombia/elecciones/articulo/que-tanto-influyen-las-redes-sociales-en-la-opinion-politica-de-los-colombianos-estos-son-los-riesgos-que-ha-detectado-la-registraduria/202631/)
- [Publimetro — Estudio Kaspersky](https://www.publimetro.co/tecnologia/2026/05/26/cuidado-al-dar-sus-datos-para-las-elecciones-alertan-hackeos-y-robos-a-una-semana-de-las-votaciones/)

**Consumo de noticias**

- [Reuters Institute — Digital News Report 2026](https://reutersinstitute.politics.ox.ac.uk/es/digital-news-report/2026) y [capítulo Colombia](https://reutersinstitute.politics.ox.ac.uk/es/digital-news-report/2026/colombia)
- [Vanguardia — Confianza e interés político (DNR 2026)](https://www.vanguardia.com/entretenimiento/tendencias/2026/07/28/estudio-revela-que-tendencia-politica-consume-mas-noticias-de-influencers-y-creadores-en-colombia/)
- [Cambio — Confianza en la IA para informarse](https://cambiocolombia.com/pais/articulo/2026/7/que-tanto-confian-los-colombianos-en-la-ia-para-informarse-esto-revelo-un-estudio)
- [Radio Nacional — Plataformas (DNR 2025)](https://radionacional.co/actualidad/rtvc-noticias-segundo-medio-mas-confiable-segun-digital-news-report-2025)

**Evidencia sobre verificación y polarización**

- [Walter et al. — Meta-análisis de fact-checking](https://cris.haifa.ac.il/en/publications/fact-checking-a-meta-analysis-of-what-works-and-for-whom/)
- [Nieman Lab — Identidad partidista vs correcciones](https://www.niemanlab.org/2023/06/when-it-comes-to-misinformation-partisanship-overpowers-fact-checking-over-and-over-again/)
- [OUP — Sobre el efecto rebote](https://educationblog.oup.com/theory-of-knowledge/facts-matter-after-all-rejecting-the-backfire-effect)
- [DFRLab — Desinformación y polarización](https://dfrlab.org/2020/06/23/hearts-and-minds-misinformation-polarization-and-resistance-to-fact-checking/)
- [Stanford — Strengthening Democracy Challenge](https://sociology.stanford.edu/scalable-interventions-reduce-polarization-support-partisan-violence-and-anti-democratic-attitudes)
- [Northwestern — Polarización y actitudes antidemocráticas](https://news.northwestern.edu/stories/2022/10/partisans-willing-to-upend-democracy-to-help-their-party-win-even-when-polarization-is-diminished)
- [More in Common — Overcoming Distrust](https://www.moreincommon.com/media/gqxcdxfb/mic_overcoming-distrust-experiment_report.pdf)
- [MIT Sloan — Diálogos con IA y conspiraciones (Science 2024)](https://mitsloan.mit.edu/node/48296)

**Community Notes y bridging**

- [arXiv 2510.00650 — Sostenibilidad de Community Notes](https://arxiv.org/pdf/2510.00650)
- [arXiv 2512.19947 — Participación y dependencia de verificadores](https://arxiv.org/pdf/2512.19947)
- [arXiv 2410.12699 — Bridging y contradiscurso](https://arxiv.org/pdf/2410.12699)
- [arXiv 2511.02615 — Sesgo y manipulación de evaluadores](https://arxiv.org/pdf/2511.02615)
- [arXiv 2606.30905 — Notas generadas con IA](https://arxiv.org/pdf/2606.30905)
- [arXiv 2609.21496 — Dos ejes de polarización](https://arxiv.org/pdf/2609.21496)
- [ICIP — Algoritmos de bridging para despolarizar](https://www.icip.cat/perlapau/en/article/bridging-algorithms-as-practical-tools-for-depolarisation/)
- [Long-term Wiki — Polis](https://www.longtermwiki.com/wiki/E2718)

**Ecosistema de verificación, regulación y financiación**

- [Chequeado — Chatbot en WhatsApp](https://chequeado.com/?p=32183)
- [Poynter — Estado de los verificadores](https://poynter.org/?p=1153978)
- [Duke Reporters' Lab — Censo 2026](https://reporterslab.org/?p=4294)
- [Buenos Aires Times — Meta prueba Community Notes en LatAm](https://batimes.com.ar/news/culture/meta-tests-fact-check-replacement-in-latin-america.phtml)
- [OCDE — Proyecto de ley de IA en Colombia](https://oecd.ai/en/dashboards/policy-initiatives/artificial-intelligence-bill-in-colombia)
- [Gaceta del Congreso 878 de 2026](https://www.redjurista.com/Compilaciones2018/gacetasCongreso/2026/gc_0878_2026.pdf)
- [Impacto TIC — Agenda TIC 2026](https://impactotic.co/innovacion/elecciones-2026-colombia-la-agenda-tic-que-definira-al-pais/)

Nota: varias cifras vienen de notas de prensa que resumen informes (Digital News Report, MOE, IFCN); antes de usarlas en una presentación a financiadores, conviene citarlas del informe original.
