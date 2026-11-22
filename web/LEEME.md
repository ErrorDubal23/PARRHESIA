# App web · Parrhesia

React 18 + Vite 5 + TypeScript (decisión 15). Estilos propios con variables (tema claro y oscuro), sin frameworks de estilos. Logo: fuente única en `src/marca.ts` (dos "P" en espejo con forma sutil de mariposa). El componente `<Logo>` lo dibuja con aleteo opcional (`siempre` en el acceso, `al-pasar` en la barra lateral; quieto si el sistema pide menos movimiento). `npm run marca` regenera `public/logo.svg`, `public/favicon.svg` y `diagramas/marca/*.svg`.

Pantalla de acceso: panel con el relieve real de Colombia en puntillismo (`src/datos/relieve_colombia.json`, 4.896 puntos generados por `scripts/generar_relieve.py` desde NOAA ETOPO1 y Natural Earth, ambos de dominio público), dibujado una vez en un `<canvas>` sobre un plano con perspectiva que se inclina levemente con el puntero, y mariposas con la forma del logo en vuelo lento. Se carga solo en esa pantalla. Sin datos oficiales: las cifras viven dentro de la app.

Formato de las publicaciones (`src/formato.ts`): `**negrita**`, `*cursiva*` y `[texto](https://…)`, guardado como marcas de texto y dibujado con elementos de React (nunca HTML). Las reglas son las mismas de `util.texto_plano` en la base; `node --experimental-strip-types scripts/probar_formato.mjs` lo comprueba con los casos de `tests/datos/casos_formato.json`. Los enlaces solo aceptan https y muestran siempre su dominio.

Rutas: `componentes/Protegida.tsx` pide sesión (y rol cuando corresponde) y devuelve a la página de origen después de entrar; `componentes/NoEncontrado.tsx` es la página 404/403 y la que muestran las páginas cuando lo que buscan no existe. El servidor revisa los permisos en cada petición: la protección en la app solo evita mostrar pantallas que no cargarían. Como es una app de una sola página, Nginx responde 200 a cualquier ruta y la app muestra el 404.

Tipografía (decisión 32, "Claridad"): Bricolage Grotesque para títulos y cifras destacadas, Atkinson Hyperlegible Next para el texto y Atkinson Hyperlegible Mono para tablas. Todas OFL, alojadas en el propio servidor.

```bash
npm install
npm run dev      # http://localhost:5173 (la API va a la puerta de entrada de Docker, http://localhost:8080)
npm run build    # lo hace el Dockerfile de la puerta de entrada
```

En Docker, la puerta de entrada (`gateway/Dockerfile`) compila la app y la sirve en <http://localhost:8080> junto con la API.

Reglas de diseño:
- **Neutral:** paleta negro, arena y crema; ningún color de partido político. Las conclusiones se distinguen por forma (glifos), nunca por verde o rojo, y nunca dicen "verdadero" o "falso".
- **Solo datos reales:** las gráficas se dibujan con la serie oficial de la API; si no hay datos, no se dibuja nada.
- **Sin cápsulas genéricas:** las marcas son sellos tipográficos (versalitas espaciadas, sin filetes ni líneas decorativas) y fichas con la esquina doblada.
- **Cifras como texto:** llegan exactas de la API; solo se redondean para mostrarse (decisión 27), con el valor exacto en el `title`.
