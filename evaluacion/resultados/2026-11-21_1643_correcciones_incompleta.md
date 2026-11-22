> **Corrida incompleta: no cuenta como medición.** El cupo diario gratuito de OpenRouter (segundo lector del consenso) se agotó a las 21:08 UTC; 13 de las 28 publicaciones no tuvieron segunda lectura y, como debe ser, no recibieron conclusión. Se repite cuando se reinicie el cupo.

# Evaluación v1 · correcciones · 2026-11-21T16:43:37

**Aciertos: 14 de 30** (meta: 24). Evaluables: 28. Con dato oficial disponible: 1 de 7.

Las expectativas están en `evaluacion/afirmaciones_v1.yaml` y se fijaron antes de correr.

| # | Categoría | Resultado | Lo que leyó y concluyó el sistema | Esperado |
| --- | --- | --- | --- | --- |
| 1 | sin_serie | ✔  | kidnapping · — · — · 79 → **requiere_revision** (brechas: —) | No hay serie oficial de secuestro conectada; además es un cambio que la fuente no publica. Lo correcto es no dar veredicto. |
| 2 | sin_serie | ✔  | sin afirmaciones verificables (estado requiere_revision) | Sin serie de extorsión. No se aproxima con otra fuente. |
| 3 | variacion | ✔  | sin afirmaciones verificables (estado sin_cifras) | Masacres no es una serie del catálogo y el cambio porcentual no lo publica la fuente. |
| 4 | variacion | ✔  | homicides · conteo · — · 64 → **requiere_revision** (brechas: —) | La serie de homicidios publica conteos mensuales, no ese cambio; calcularlo no está permitido. |
| 5 | sin_serie | ✔  | theft · — · — · 24 → **sin_dato_comparable** (brechas: —) | Sin serie de hurtos conectada. |
| 6 | con_dato | ✔  | homicides · conteo · 2026-08 · 499 → **se_debilita** (brechas: dato_provisional, nota_serie)<br>homicides · conteo · 2026-08 · 717 → **se_debilita** (brechas: dato_provisional, nota_serie) | El dato oficial de agosto de 2026 (Policía Nacional, SIEDCO) es 1.190 y es provisional. Ninguna de las dos cifras coincide. |
| 7 | sin_serie | ✔  | theft · — · — · 49 → **sin_dato_comparable** (brechas: —) | Sin serie de hurtos. |
| 8 | sin_serie | ✔  | extortion · — · — · 46 → **requiere_revision** (brechas: —) | Sin serie de extorsión. |
| 9 | sin_cifra | ✔  | sin afirmaciones verificables (estado sin_cifras) | El registro original no trae la cifra. Sin cifra es una opinión; además solo hay series nacionales. |
| 10 | variacion | ✔  | minimum_wage · — · 2026 · 23.7 → **sin_dato_comparable** (brechas: —) | El cambio no lo publica la fuente y la serie del salario mínimo no tiene datos aceptados. |
| 11 | sin_serie | ✔  | minimum_wage · nominal · — · 1750905 → **sin_dato_comparable** (brechas: —) | La serie del salario mínimo no tiene datos aceptados (suspensión del decreto registrada en sus notas). |
| 12 | con_dato | ✘ falta una afirmación que cumpla {'valor': '5.10', 'conclusion': 'se_sostiene'} | inflation · anual · — · 5.1 → **requiere_revision** (brechas: —)<br>minimum_wage · — · — · 17.9 → **requiere_revision** (brechas: —) | La inflación anual a diciembre de 2025 fue 5,10 % (DANE). Los 17,9 puntos son un cambio no publicado y no deben recibir veredicto. |
| 13 | sin_cifra | ✔  | sin afirmaciones verificables (estado sin_cifras) | Es una proyección sin cifra exacta: se publica como opinión. |
| 14 | sin_cifra | ✔  | sin afirmaciones verificables (estado sin_cifras) | El único número es un año. No hay cifra del indicador que verificar. |
| 15 | con_dato | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | No dice a qué periodo corresponde la inflación; sin periodo no hay dato comparable. Productividad no es un indicador del catálogo. |
| 16 | con_dato | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | 6,29 % coincide con el DANE. El cambio de 1,11 puntos no lo publica la fuente y no debe recibir veredicto (menos aún "se debilita"). |
| 17 | con_dato | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | 0,39 % es la variación mensual; la anual de agosto fue 6,24 %. Acierta si señala que no dice qué variación cita o que la cifra es de otra variante. Darla por buena sin más es no detectar la trampa. |
| 18 | proyeccion | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Es una proyección, no un dato observado. Verificarla como si fuera una afirmación sobre el dato sería un error. |
| 19 | con_dato | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | El DANE da 8,1 % para julio de 2026. Los 0,7 puntos son un cambio no publicado. |
| 20 | con_dato | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Las cifras coinciden, pero agosto de 2026 tiene una nota oficial (ajuste de los factores de expansión por el sismo del 10 de agosto) que debe acompañar el dato. |
| 21 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Relaciones laborales (RELAB) no es una serie del catálogo, y el 0,4 % no es una tasa de desempleo. |
| 22 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Sin serie de deuda pública conectada. |
| 23 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Sin serie de deuda pública. |
| 24 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Sin serie de deuda pública. |
| 25 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Sin serie de deuda pública. |
| 26 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Sin serie de deuda pública. |
| 27 | sin_serie | ✘ la verificación no terminó a tiempo | la verificación no terminó a tiempo | Sin serie de deuda pública. |
| 28 | no_evaluable | — no evaluable | no evaluable | Plantilla de una gráfica con el eje recortado. Es una imagen, no un texto, y la v1 solo lee texto. |
| 29 | sin_cifra | ✔  | sin afirmaciones verificables (estado sin_cifras) | Plantilla sin caso real ni cifra. Una percepción no es un registro oficial; se publica como opinión. |
| 30 | no_evaluable | — no evaluable | no evaluable | Plantilla sin caso real. Inventar la cifra de inflación de alimentos rompería la regla de no inventar números. |
