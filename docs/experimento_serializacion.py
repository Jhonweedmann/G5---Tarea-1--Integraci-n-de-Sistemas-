"""Mide tamaño y tiempo de serialización de un Curso protobuf frente a JSON."""
import json
import statistics
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "cupos"))
from app.cupos_pb2 import Curso

N = 10_000
curso = Curso(id="ARQ-101", nombre="Arquitectura de Sistemas", cupos_totales=40, cupos_disponibles=12)
objeto = {"id": curso.id, "nombre": curso.nombre, "cupos_totales": curso.cupos_totales, "cupos_disponibles": curso.cupos_disponibles}


def medir(fn):
    muestras = []
    for _ in range(10):
        inicio = time.perf_counter_ns()
        for _ in range(N):
            salida = fn()
        muestras.append((time.perf_counter_ns() - inicio) / N)
    return len(salida), statistics.mean(muestras), statistics.stdev(muestras)


for nombre, fn in (("protobuf", curso.SerializeToString), ("json", lambda: json.dumps(objeto, separators=(",", ":")).encode())):
    bytes_, media, desviacion = medir(fn)
    print(f"{nombre}: {bytes_} bytes; {media:.0f} ns/op ± {desviacion:.0f}")
