# Recorridos de la página (auditoría, bloque 4)

Usan Chrome real con `puppeteer-core`, que no es dependencia del proyecto: instálalo en una carpeta aparte
(`npm install puppeteer-core@23.11.1`) y copia ahí estos archivos.

| Archivo | Qué prueba | Necesita |
|---|---|---|
| `recorrido_a.mjs` | Crear cuenta, publicar, triple clic, reacciones, compartir, responder, retirar (FN-01 a FN-06). Crea una cuenta de prueba y la desactiva | — |
| `recorrido_b.mjs` | Verificación, analizar, temas, tendencias, comunidades, figuras, búsqueda, coherencia de conteos y navegación (FN-07 a FN-20) | `CLAVE_DEMO`, `IDS` |
| `barrido.mjs` | Todas las rutas en escritorio, celular, claro, oscuro y sin sesión: errores, 5xx, textos rotos y desbordes | `CLAVE_DEMO`, `IDS` |
| `teclado.mjs` | Uso solo con teclado (FN-18) | `CLAVE_DEMO` |
| `navegacion.mjs` | Al navegar, cada página nueva empieza arriba (A2-15) | `CLAVE_DEMO` |

`CLAVE_DEMO` es la clave que imprime `db/semillas/demo.py` al sembrar (nunca se escribe en el código).
`IDS` es un JSON con ids reales: `pub` (publicación con conclusión), `figura`, `tema`, `comunidad_publica`,
`comunidad_privada`, `serie`, `dato`, `enlace` y `etiqueta`.

Cada interacción deja rastros reales en la base (respuestas, reacciones, cuentas de prueba desactivadas): correr
antes de resembrar la demo, no después.
