"""Mide cómo responde la API REST mientras Cupos está detenido y cuánto tarda en recuperarse.

Requiere el sistema levantado con Docker Compose. Uso:
    python docs/experimento_resiliencia.py [--proyecto NOMBRE] [--repeticiones 3] [--duracion 40]

Se consulta un curso inexistente: con Cupos arriba responde 404 (que no se guarda en caché),
así Redis no oculta la caída.
"""
import argparse
import json
import statistics
import subprocess
import time
import urllib.error
import urllib.request

URL = "http://localhost:8000/v1/cursos/NO-EXISTE"
TOKEN = "desarrollo-seguro"


def consultar():
    peticion = urllib.request.Request(URL, headers={"Authorization": f"Bearer {TOKEN}"})
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(peticion, timeout=10) as respuesta:
            codigo = respuesta.status
    except urllib.error.HTTPError as error:
        codigo = error.code
    except (urllib.error.URLError, TimeoutError):
        codigo = 0
    return codigo, (time.perf_counter() - inicio) * 1000


def compose(proyecto, *args):
    base = ["docker", "compose"] + (["-p", proyecto] if proyecto else [])
    subprocess.run(base + list(args), check=True, capture_output=True)


def esperar(codigo_esperado, limite=60):
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < limite:
        if consultar()[0] == codigo_esperado:
            return time.perf_counter() - inicio
        time.sleep(0.2)
    raise RuntimeError(f"la API no volvió a responder {codigo_esperado} en {limite} s")


def repeticion(proyecto, duracion, intervalo):
    esperar(404)
    compose(proyecto, "stop", "cupos")
    detenido = time.perf_counter()
    muestras = []
    while time.perf_counter() - detenido < duracion:
        codigo, ms = consultar()
        muestras.append({"t": round(time.perf_counter() - detenido, 2), "codigo": codigo, "ms": round(ms, 1)})
        time.sleep(intervalo)
    compose(proyecto, "start", "cupos")
    recuperacion = esperar(404)
    return muestras, recuperacion


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proyecto", default=None)
    parser.add_argument("--repeticiones", type=int, default=3)
    parser.add_argument("--duracion", type=float, default=40)
    parser.add_argument("--intervalo", type=float, default=1)
    args = parser.parse_args()

    resultados = []
    for i in range(args.repeticiones):
        muestras, recuperacion = repeticion(args.proyecto, args.duracion, args.intervalo)
        primer_503 = next((m["t"] for m in muestras if m["codigo"] == 503), None)
        resultados.append({"muestras": muestras, "recuperacion_s": round(recuperacion, 2), "primer_503_s": primer_503})
        print(f"Repetición {i + 1}: primer 503 a los {primer_503} s; recuperación en {recuperacion:.2f} s")

    print("\nResumen por código de estado (todas las repeticiones):")
    for codigo in sorted({m["codigo"] for r in resultados for m in r["muestras"]}):
        tiempos = [m["ms"] for r in resultados for m in r["muestras"] if m["codigo"] == codigo]
        print(f"  {codigo}: {len(tiempos)} respuestas; latencia media {statistics.mean(tiempos):.1f} ms,"
              f" mín {min(tiempos):.1f}, máx {max(tiempos):.1f}")
    transiciones = [r["primer_503_s"] for r in resultados if r["primer_503_s"] is not None]
    if len(transiciones) > 1:
        print(f"  Paso de 504 a 503: media {statistics.mean(transiciones):.1f} s ± {statistics.stdev(transiciones):.1f}")
    print(json.dumps(resultados, ensure_ascii=False), file=open("resiliencia_resultados.json", "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
