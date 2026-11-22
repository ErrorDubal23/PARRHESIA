# Evaluación control · correcciones · 2026-11-21T21:04:29

**Aciertos: 9 de 10** (meta: 8). Evaluables: 10. Con dato oficial disponible: 6 de 7.

Las expectativas están en `evaluacion/afirmaciones_control.yaml` y se fijaron antes de correr.

| # | Categoría | Resultado | Lo que leyó y concluyó el sistema | Esperado |
| --- | --- | --- | --- | --- |
| 1 | con_dato | ✔  | unemployment · tasa · 2026-03 · 8.8 → **se_sostiene** (brechas: nota_serie) | El DANE publica 8,79 % para marzo de 2026; dicho con un decimal es 8,8 %. |
| 2 | con_dato | ✔  | inflation · anual · 2026-07 · 6.03 → **se_debilita** (brechas: periodo_limitado) | La cifra coincide, pero que haya bajado depende de con qué se compare: frente a junio (6,14 %) bajó; frente a julio de 2025 (4,90 %) subió. |
| 3 | con_dato | ✔  | unemployment · tasa · 2026-08 · 9.4 → **se_invierte** (brechas: nota_serie) | La cifra coincide (9,36 %), pero subió frente a julio (8,10 %) y frente a agosto de 2025 (8,60 %). Además ese mes tiene la nota oficial del sismo. |
| 4 | con_dato | ✔  | inflation · anual · 2026-07 · 0.17 → **se_debilita** (brechas: variante_equivocada) | 0,17 % es la variación mensual de julio de 2026; la anual fue 6,03 %. |
| 5 | con_dato | ✔  | unemployment · tasa · 2026-05 · 8.8 → **se_debilita** (brechas: nota_serie, periodo_limitado) | El dato de mayo de 2026 es 8,02 %; 8,8 % es el de abril (8,78 %). |
| 6 | con_dato | ✔  | homicides · conteo · 2025-10 · 1112 → **se_sostiene** (brechas: nota_serie) | Coincide con el conteo de la Policía Nacional para octubre de 2025. |
| 7 | con_dato | ✘ falta una afirmación que cumpla {'valor': '5.74', 'conclusion': 'se_sostiene'} | inflation · anio_corrido · — · 5.74 → **requiere_revision** (brechas: —) | La variación año corrido a septiembre de 2026 es 5,74 % (DANE). |
| 8 | sin_serie | ✔  | unemployment · tasa · 2026-07 · 8.5 → **sin_dato_comparable** (brechas: —) | Solo hay series nacionales registradas; no se compara una ciudad con el total del país. |
| 9 | proyeccion | ✔  | sin afirmaciones verificables (estado sin_cifras) | Es una proyección, no un dato observado. |
| 10 | sin_cifra | ✔  | sin afirmaciones verificables (estado sin_cifras) | No hay cifra: se publica como opinión. |
