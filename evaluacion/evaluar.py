"""Evaluación del sistema con un conjunto de prueba. Meta: el 80 % de las afirmaciones (24 de 30 en la v1).

    uv run python evaluacion/evaluar.py [--conjunto v1|control] [--base http://127.0.0.1:8080] [--etiqueta linea_base]

Conjuntos: v1 (las 30 afirmaciones de docs/PROYECTO.md) y control (10 afirmaciones nuevas, escritas después
de las correcciones de la v1 y antes de correrlas, para saber si el sistema mejoró o solo se ajustó a la v1).

Corre de punta a punta como lo haría una persona: crea una cuenta de un solo uso, publica cada
afirmación por la puerta de entrada, espera a que la verificación termine (extracción por consenso
con dos proveedores de IA, motor de reglas, validador) y califica contra lo que se esperaba
(evaluacion/afirmaciones_<conjunto>.yaml, fijado ANTES de correr). Al final retira las publicaciones y
desactiva la cuenta, y deja el informe en evaluacion/resultados/.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import secrets
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx
import yaml

AQUI = Path(__file__).resolve().parent
TERMINADOS = {"lista", "sin_cifras", "requiere_revision"}


def igual(a: str | None, b: str) -> bool:
    try:
        return a is not None and Decimal(a) == Decimal(b)
    except InvalidOperation:
        return False


def con_brecha(af: dict) -> set[str]:
    v = af.get("verificacion") or {}
    return {p["codigo"] for p in v.get("pruebas") or [] if p["resultado"] == "con_brecha"}


def cumple(spec: dict, af: dict) -> bool:
    v = af.get("verificacion") or {}
    if "valor" in spec and not igual(af.get("valor_dicho"), spec["valor"]):
        return False
    if "conclusion" in spec and v.get("conclusion") != spec["conclusion"]:
        return False
    if "prueba" in spec and spec["prueba"] not in con_brecha(af):
        return False
    if "motivo_contiene" in spec and spec["motivo_contiene"] not in (v.get("explicacion") or "").lower():
        return False
    guia = af.get("guia") or {}
    if "consejo" in spec and spec["consejo"] not in {c["codigo"] for c in guia.get("consejos", [])}:
        return False
    if spec.get("con_fuente") and not guia.get("fuentes"):
        return False
    return True


JUICIOS = re.compile(r"(mentir|mentira|falso|falsa|enga[ñn]|manipul|propaganda|desinform|miente|confiable|proviene)", re.I)


def guias_limpias(afs: list[dict]) -> str | None:
    """Decisión 34: ninguna guía redactada por la IA lleva cifras ni juicios (se revisa en todos los conjuntos)."""
    for af in afs:
        texto = (af.get("guia") or {}).get("redaccion")
        if texto and (re.search(r"[0-9]", texto) or JUICIOS.search(texto)):
            return f"una guía redactada lleva cifras o juicios: {texto!r}"
    return None


def calificar(fila: dict, resultado: dict) -> tuple[bool, str]:
    """¿El sistema hizo lo que se esperaba? Devuelve (acierto, explicación corta)."""
    esperado = fila["esperado"]
    afs = resultado.get("afirmaciones", [])
    conclusiones = [(af.get("verificacion") or {}).get("conclusion") for af in afs]
    usadas: set[int] = set()
    for spec in esperado.get("requiere", []):
        indice = next((i for i, af in enumerate(afs) if i not in usadas and cumple(spec, af)), None)
        if indice is None:
            return False, f"falta una afirmación que cumpla {spec}"
        usadas.add(indice)
    if "alguna_de" in esperado and not any(cumple(s, af) for s in esperado["alguna_de"] for af in afs):
        return False, "no se cumple ninguna de las alternativas esperadas"
    sucia = guias_limpias(afs)
    if sucia:
        return False, sucia
    prohibidas = esperado.get("ninguna_conclusion", []) + esperado.get("ninguna_conclusion_salvo_requeridas", [])
    for i, c in enumerate(conclusiones):
        if i not in usadas and c in prohibidas:
            return False, f"dio un veredicto que no correspondía: {c}"
    return True, "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conjunto", default="v1", choices=["v1", "control", "guias"])
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--etiqueta", default="corrida")
    parser.add_argument("--espera-max", type=int, default=2400, help="segundos para esperar la verificación")
    args = parser.parse_args()
    filas = yaml.safe_load((AQUI / f"afirmaciones_{args.conjunto}.yaml").read_text())
    api = httpx.Client(base_url=f"{args.base}/api", timeout=30, headers={"X-Parrhesia": "1"})

    # Cuenta de un solo uso (la clave no se guarda en ningún lado).
    marca = datetime.now().strftime("%Y%m%d%H%M%S")  # con segundos: dos corridas en el mismo minuto
    nombre, clave = f"evaluacion_{marca}", secrets.token_urlsafe(18)
    api.post("/social/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": f"Evaluación {args.conjunto}",
                                         "correo": f"{nombre}@evaluacion.parrhesia.local", "clave": clave}).raise_for_status()
    api.post("/social/v1/sesiones", json={"correo": f"{nombre}@evaluacion.parrhesia.local", "clave": clave}).raise_for_status()

    publicadas: dict[int, str] = {}
    for fila in filas:
        if fila.get("texto"):
            r = api.post("/social/v1/publicaciones", json={"texto": fila["texto"]})
            r.raise_for_status()
            publicadas[fila["n"]] = r.json()["id"]
    print(f"publicadas {len(publicadas)} afirmaciones como @{nombre}; esperando la verificación…", flush=True)

    resultados: dict[int, dict] = {}
    inicio = time.monotonic()
    while len(resultados) < len(publicadas) and time.monotonic() - inicio < args.espera_max:
        for n, pid in publicadas.items():
            if n in resultados:
                continue
            r = api.get(f"/verificacion/v1/textos/publicacion/{pid}")
            # Terminada = estado final Y ninguna afirmación esperando su verificación: una publicación con una
            # cifra en revisión y otra que se sigue verificando ya dice "requiere_revision" (corrida del 21 nov).
            if (r.status_code == 200 and r.json()["estado"] in TERMINADOS
                    and not any(a["estado"] == "extraida" and a["verificacion"] is None for a in r.json()["afirmaciones"])):
                resultados[n] = r.json()
        print(f"  {len(resultados)}/{len(publicadas)} terminadas ({int(time.monotonic() - inicio)} s)", flush=True)
        if len(resultados) < len(publicadas):
            time.sleep(15)

    filas_informe, aciertos = [], 0
    for fila in filas:
        n = fila["n"]
        if fila["categoria"] == "no_evaluable":
            filas_informe.append({**fila, "acierto": False, "nota": "no evaluable", "resultado": None})
            continue
        resultado = resultados.get(n)
        if resultado is None:
            filas_informe.append({**fila, "acierto": False, "nota": "la verificación no terminó a tiempo", "resultado": None})
            continue
        acierto, nota = calificar(fila, resultado)
        aciertos += acierto
        filas_informe.append({**fila, "acierto": acierto, "nota": nota, "resultado": resultado})

    evaluables = sum(1 for f in filas if f["categoria"] != "no_evaluable")
    con_dato = [f for f in filas_informe if f["categoria"] == "con_dato"]
    resumen = {
        "conjunto": args.conjunto, "etiqueta": args.etiqueta, "fecha": datetime.now().isoformat(timespec="seconds"),
        "aciertos": aciertos, "total": len(filas), "evaluables": evaluables, "meta": math.ceil(0.8 * len(filas)),
        "aciertos_con_dato": sum(f["acierto"] for f in con_dato), "total_con_dato": len(con_dato),
    }
    destino = AQUI / "resultados"
    destino.mkdir(exist_ok=True)
    nombre_archivo = f"{datetime.now():%Y-%m-%d_%H%M}_{args.conjunto}_{args.etiqueta}"
    (destino / f"{nombre_archivo}.json").write_text(json.dumps({"resumen": resumen, "filas": filas_informe},
                                                               ensure_ascii=False, indent=2, default=str))
    (destino / f"{nombre_archivo}.md").write_text(informe(resumen, filas_informe))
    print(json.dumps(resumen, ensure_ascii=False))

    # Limpieza: las publicaciones se retiran (sus verificaciones quedan) y la cuenta se desactiva.
    for pid in publicadas.values():
        api.delete(f"/social/v1/publicaciones/{pid}")
    api.post("/social/v1/yo/desactivacion", json={"clave_actual": clave})


def lectura(af: dict) -> str:
    v = af.get("verificacion") or {}
    brechas = ", ".join(sorted(con_brecha(af))) or "—"
    return (f"{af.get('indicador') or '—'} · {af.get('variante') or '—'} · {af.get('periodo') or '—'} · "
            f"{af.get('valor_dicho') or '—'} → **{v.get('conclusion') or af.get('estado')}** (brechas: {brechas})")


def informe(resumen: dict, filas: list[dict]) -> str:
    lineas = [
        f"# Evaluación {resumen['conjunto']} · {resumen['etiqueta']} · {resumen['fecha']}",
        "",
        f"**Aciertos: {resumen['aciertos']} de {resumen['total']}** (meta: {resumen['meta']}). "
        f"Evaluables: {resumen['evaluables']}. Con dato oficial disponible: {resumen['aciertos_con_dato']} de {resumen['total_con_dato']}.",
        "",
        f"Las expectativas están en `evaluacion/afirmaciones_{resumen['conjunto']}.yaml` y se fijaron antes de correr.",
        "",
        "| # | Categoría | Resultado | Lo que leyó y concluyó el sistema | Esperado |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in filas:
        r = f.get("resultado")
        if r is None:
            leido = f["nota"]
        elif not r.get("afirmaciones"):
            leido = f"sin afirmaciones verificables (estado {r['estado']})"
        else:
            leido = "<br>".join(lectura(af) for af in r["afirmaciones"])
        marca = "✔" if f["acierto"] else ("—" if f["categoria"] == "no_evaluable" else "✘")
        lineas.append(f"| {f['n']} | {f['categoria']} | {marca} {'' if f['acierto'] else f['nota']} | {leido} | {f['por_que']} |")
    return "\n".join(lineas) + "\n"


if __name__ == "__main__":
    main()
