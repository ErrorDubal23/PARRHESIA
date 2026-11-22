# Servicio de IA independiente de la cuenta

Versión 2 (20 nov 2026). Nombres en español sin tildes (decisión 14, [glosario](glosario_codigo.md)).

## El problema

Groq tiene un cupo gratuito por cuenta. Si una cuenta llega a su límite, la verificación no debe detenerse ni cambiar de comportamiento, y la app no debe enterarse de qué cuenta se usó.

## La solución: la IA es un servicio aparte, sin sesión

```
app ──► servicio social ──► servicio de verificación ──► ia.trabajo (cola en PostgreSQL)
                                     ▲                         │
                                     │                         ▼
                                     └── resultado validado ◄── servicio de IA ──► Groq (cuenta 1, 2, 3…)
```

1. **La app nunca llama a la IA.** Publica en el servicio social y luego lee el estado de la verificación ("pendiente", "lista").
2. **El servicio de verificación pide trabajos, no respuestas.** Escribe un trabajo en `ia.trabajo` con su tipo, su entrada y la versión del prompt. No sabe qué proveedor ni qué cuenta lo va a resolver.
3. **El servicio de IA toma trabajos de la cola** con `SELECT ... FOR UPDATE SKIP LOCKED` dentro de una transacción. Así varios trabajadores no toman el mismo trabajo.
4. **Elige una credencial disponible:** habilitada y sin pausa. Las llaves secretas están en la configuración del contenedor, cada una con su alias (`GROQ_KEY_groq_cuenta_1`, `GROQ_KEY_groq_cuenta_2`…). La base solo guarda el alias y su estado.
5. **Si el proveedor responde "límite alcanzado"** (HTTP 429), esa credencial queda en pausa hasta la hora que indique el proveedor, el intento se registra y el trabajo pasa a la siguiente credencial.
6. **Si todas están en pausa**, el trabajo vuelve a la cola con `proximo_intento_en` en el futuro. Nada se cae: la publicación sigue visible con "verificación pendiente".
7. **El resultado se valida contra un formato fijo** (JSON Schema versionado en el repositorio) antes de guardarse. Si no lo cumple, se registra como `salida_invalida` y se reintenta. Lo que llega al servicio de verificación siempre tiene la misma forma, venga de la cuenta que venga.
8. **Caché:** si ya hay un trabajo terminado con el mismo tipo, la misma versión del prompt y la misma entrada (`huella_entrada`), se reutiliza su resultado y no se llama a Groq.

## Dos proveedores y extracción por consenso (decisión 26)

| Proveedor | Cuentas | Modelos | Papel |
| --- | --- | --- | --- |
| Groq | `groq_cuenta_1`, `groq_cuenta_2` (respaldo entre sí) | `openai/gpt-oss-120b` (leer), `openai/gpt-oss-20b` (redactar) | Primer lector y redactor |
| OpenRouter | `openrouter_1` (plan gratuito) | `nvidia/nemotron-3-ultra-550b`, y si está saturado, `baidu/ernie-5.5-flash`, `nvidia/nemotron-3.5-super-vl`, `google/gemma-4-31b` | Segundo lector independiente (otro fabricante) |

Cada texto que pasa el filtro previo se lee dos veces, una en cada proveedor. La base compara las lecturas (`verificacion.lecturas_coinciden`): si dicen lo mismo, sigue el motor de reglas; si no, la afirmación queda en revisión. Los modelos gratuitos de OpenRouter comparten cupo con todos sus usuarios: un 429 "upstream" es del modelo, no de la cuenta, y el servicio prueba el siguiente modelo antes de pausar la cuenta. Prueba en vivo del 21 nov 2026: los dos lectores dieron la misma lectura de "en septiembre de 2026 el desempleo fue de 8,9 %".

**Redacción (versión 2 del prompt, 21 nov 2026).** En la primera prueba real, la IA escribió en una explicación que el valor "corresponde a otro periodo", lo cual no era cierto: todas sus cifras eran correctas, así que el validador de cifras no lo podía detectar. Desde la versión 2, la IA recibe la explicación ya armada por las reglas y solo puede decir lo mismo con mejores palabras, sin agregar causas, brechas ni afirmaciones. En Groq, `gpt-oss` corre con razonamiento bajo y espacio suficiente para el JSON (antes, a veces se quedaba sin tokens).

Los prompts están en `src/servicios/ia/prompts/<tipo>.v<n>.md`. Un prompt ya usado no se cambia: se crea la versión siguiente, y la caché no mezcla versiones.

## Cambiar o agregar una cuenta

1. Agregar la llave al archivo de secretos del contenedor del servicio de IA, con un alias nuevo.
2. Insertar el alias en `ia.credencial` (o habilitarlo).
3. Reiniciar solo el servicio de IA. La app, la base y los demás servicios no se tocan.

Para cambiar de proveedor (por ejemplo, de Groq a otro), se agrega un adaptador nuevo detrás de la misma interfaz: recibe el prompt y el formato esperado, y devuelve texto o un error clasificado (`limite_alcanzado`, `error_proveedor`). El resto del sistema no cambia.

## Qué hace la IA y qué no

| Tarea | IA | Reglas y base de datos |
| --- | --- | --- |
| Leer la publicación y extraer la afirmación (indicador, variante, periodo, territorio, valor dicho) | Sí, `openai/gpt-oss-120b` en Groq | |
| Agrupar las noticias de la ventana en temas, con un título neutral | Sí (`agrupar_temas`) | Contar medios, descartar temas con menos de 3, ordenar y validar que los artículos existan |
| Extraer de los artículos de un tema las declaraciones con cifras (actor y cita) | Sí (`extraer_declaraciones`) | Revisar que la cita esté textual en el artículo; ligar el actor a una figura registrada solo si coincide exactamente |
| Decidir si un texto pasa a la IA | | Sí: filtro previo con cifras y palabras clave |
| Elegir la serie oficial | | Sí (si no hay una que coincida exactamente: "sin dato comparable") |
| Traer el valor oficial | | Sí (solo observaciones aceptadas) |
| Pruebas de robustez y conclusión | | Sí |
| Redactar la explicación en lenguaje neutral | Sí, `openai/gpt-oss-20b` en Groq | El validador rechaza cualquier número que no esté en la evidencia |

Los modelos son los que ya usaste en My_Alice; se confirman al implementar, junto con el modo de respuesta JSON que ofrezca Groq en ese momento.

## Por qué esto también sirve para la materia

- **Transacciones y concurrencia:** tomar trabajos con `FOR UPDATE SKIP LOCKED`.
- **Restricciones:** un resultado solo existe si el trabajo terminó (`CHECK`), y no hay dos resultados para la misma entrada (índice único parcial).
- **Historial completo:** cada intento queda en `ia.intento`, con la credencial, el modelo, los tokens y el resultado, sin guardar nunca un secreto.
