# Motor de reglas de la verificación

Versión 1 (aprobada el 21 nov 2026). Código: `src/servicios/verificacion/motor.py` (sin IA, sin acceso directo a la base). Pruebas: `tests/test_motor.py` y `tests/test_verificacion_completa.py`. Evaluación de punta a punta: `evaluacion/` (conjuntos v1 y control).

Cada "sin dato comparable" lleva un código de `verificacion.motivo_sin_dato` (decisión 34): con él y con las brechas encontradas, la base arma la guía de lectura (por qué y cómo comprobarlo). La guía nunca lleva cifras.

Textos que entran al motor, todos por la misma cola y con las mismas reglas: publicaciones, declaraciones de figuras, declaraciones reportadas por medios (temas del día) y fragmentos de enlaces analizados (decisión 29, migraciones 0025 y 0026: de una página solo entran las citas cortas con una cifra que no sea un año y una palabra de los 8 indicadores).

La IA solo lee el texto (dos veces, en dos proveedores: decisión 26). La conclusión la deciden estas reglas con el dato oficial:

| Paso | Regla |
| --- | --- |
| Serie | Indicador, variante y territorio se unen a una serie aprobada (`oficial.series_candidatas`), primero la que viene directa del productor (el DANE antes que SUAMECA). Si no hay una que coincida exactamente: **sin dato comparable** |
| Variante no dicha | Solo se asume cuando el indicador tiene una sola (desempleo: tasa; salario mínimo: nominal; homicidios: conteo). La inflación sin variante es **sin dato comparable** |
| Periodo | Si el texto no dice el periodo, o el oficial no existe o está en cuarentena: **sin dato comparable**. "La inflación de 2025" es la variación anual a diciembre. Un total anual de una serie mensual sería sumar: **sin dato comparable** |
| ¿Coincide? | Con la precisión con que se dijo la cifra: "8,9" coincide con 8,94; "9" coincide de 8,5 a 9,5 |
| Coincide | **Se sostiene** |
| No coincide | **Se debilita**, buscando la brecha: si la cifra es de otra variante del mismo periodo (variante equivocada) o del mismo dato hasta 12 periodos antes (periodo limitado) |
| Dirección | Si el texto dice que subió o bajó: frente al periodo anterior y al mismo periodo del año anterior. Las dos al contrario: **se invierte**. No están de acuerdo entre sí: **se debilita** ("depende del periodo con que se compare") |
| Cambios | Un cambio que la fuente no publica (en puntos o en porcentaje, de cualquier indicador, también la inflación) no se calcula ni se compara con el nivel: **sin dato comparable** en la v1 (decisión 33) |
| Avisos | Dato provisional (seguridad, hasta el 1 de abril del año siguiente) y notas oficiales del periodo, buscadas en todas las series del mismo indicador y variante (la nota de una medición no depende del canal que la publica): se muestran, no cambian la conclusión |

La explicación la redacta la IA con las cifras de la evidencia; el validador en Python y el trigger `explicacion_cifras_respaldadas` rechazan cualquier otra cifra. Si la IA falla cinco veces, se usa la explicación armada por reglas (`explicacion_de_respaldo`).
