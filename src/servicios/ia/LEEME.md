# Servicio de IA

Toma trabajos de `ia.trabajo`, llama al proveedor y guarda el resultado validado. No tiene API: la app nunca llama a la IA (docs/diseno/03_servicio_ia.md).

| Archivo | Qué hace |
|---|---|
| `proveedores.py` | Groq, Gemini y OpenRouter (API compatible con OpenAI), sus modelos por tipo de trabajo y la lectura de llaves `<PROVEEDOR>_KEY_<alias>` (Gemini: `GEMINI_KEY_gemini_1`; su cupo gratuito es por modelo, así que un 429 o un modelo retirado pasan al siguiente) |
| `cliente.py` | Una llamada de chat; clasifica los errores: límite de la cuenta, modelo saturado o error del proveedor |
| `formatos.py` | El formato fijo de cada salida y lo que la IA no puede inventar (citas textuales, cifras que estén en el texto o en la evidencia) |
| `prompts/` | Un archivo por tipo y versión; un prompt usado no se cambia, se crea la versión siguiente |
| `trabajador.py` | Toma trabajos (`ia.tomar_trabajo`), elige cuenta (`ia.elegir_credencial`) y registra cada intento (`ia.registrar_intento`) |

```bash
uv run python -m servicios.ia.trabajador
uv run pytest -m live tests/test_servicio_ia.py     # los dos proveedores reales leen el mismo texto (gasta muy poco cupo)
```
