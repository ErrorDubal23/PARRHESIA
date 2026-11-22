# Servicio de temas del día

De qué hablan los medios y qué cifras se dijeron. Diseño: `docs/diseno/06_temas_del_dia.md`.

| Archivo | Qué hace |
|---|---|
| `recolector.py` | Los medios registrados y la lectura de sus RSS (título, resumen, enlace, fecha), con `defusedxml` |
| `trabajador.py` | Recolecta cada 3 horas; agrupa los titulares de la ventana (hasta 20 por medio, con identificadores cortos para la IA); extrae las declaraciones con cifras |
| `api.py` | Temas de la última ventana, página de un tema y lista de medios |

Medios comprobados el 21 nov 2026: El Tiempo, Semana, La Silla Vacía, Caracol Radio, Portafolio, La República, Infobae Colombia y RTVC Noticias. El Espectador (RSS vacío) y Blu Radio (sin RSS) quedan pendientes.

Límite conocido: en el plan gratuito de Groq, `gpt-oss-120b` acepta 8.000 tokens por minuto; por eso la agrupación manda solo títulos, con identificadores cortos, y hasta 20 por medio.
