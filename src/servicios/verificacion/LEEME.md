# Servicio de verificación

De un texto publicado a una verificación con evidencia oficial. Reglas: `docs/diseno/08_motor_de_reglas.md`.

| Archivo | Qué hace |
|---|---|
| `motor.py` | El motor de reglas: serie, periodo, comparación, dirección, brechas y conclusión. Sin IA, sin base |
| `trabajador.py` | Etapa 1: filtro previo y dos lecturas (consenso). Etapa 2: motor y explicación validada. Retoma donde iba si se reinicia |
| `api.py` | Lo verificado de cada texto, una verificación con su evidencia, el resumen por conclusión y la revisión humana |

```bash
uv run python -m servicios.verificacion.trabajador                  # junto con servicios.ia.trabajador
uv run uvicorn servicios.verificacion.api:app --port 8003
```
