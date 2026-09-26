"""Compara protobuf y JSON para el mensaje Curso: tamaño, tiempo de serialización y efecto de gzip."""
import gzip
import json
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).parents[1]
sys.path.insert(0, str(RAIZ))
from scripts.generar_stubs import generar  # noqa: E402

generar()
sys.path.insert(0, str(RAIZ / "cupos"))
from app.cupos_pb2 import Curso  # noqa: E402

N = 10_000
SERIES = 10


def como_dict(curso):
    return {"id": curso.id, "nombre": curso.nombre, "cupos_totales": curso.cupos_totales,
            "cupos_disponibles": curso.cupos_disponibles}


def a_json(objeto):
    return json.dumps(objeto, separators=(",", ":"), ensure_ascii=False).encode()


def medir(fn):
    muestras = []
    for _ in range(SERIES):
        inicio = time.perf_counter_ns()
        for _ in range(N):
            salida = fn()
        muestras.append((time.perf_counter_ns() - inicio) / N)
    return len(salida), statistics.mean(muestras), statistics.stdev(muestras)


def cursos(n):
    return [Curso(id=f"C-{i:04d}", nombre=f"Curso de Integracion {i}", cupos_totales=40, cupos_disponibles=i % 41)
            for i in range(n)]


curso = Curso(id="ARQ-101", nombre="Arquitectura de Sistemas", cupos_totales=40, cupos_disponibles=12)
objeto = como_dict(curso)
print(f"Python {sys.version.split()[0]} · {SERIES} series de {N} operaciones\n")
print("Parte 1: un Curso")
for nombre, fn in (("protobuf", curso.SerializeToString), ("json", lambda: a_json(objeto))):
    bytes_, media, desviacion = medir(fn)
    print(f"  {nombre:8}: {bytes_} bytes; {media:.0f} ns/op ± {desviacion:.0f}")

# ListarCursos envía un mensaje por curso (server streaming); se suma el tamaño de cada mensaje,
# sin contar los 5 bytes de encabezado que gRPC agrega por mensaje.
print("\nParte 2: n cursos, sin y con gzip (bytes)")
print(f"  {'n':>5} | {'protobuf':>9} | {'json':>9} | {'proto/json':>10} | {'pb+gzip':>8} | {'json+gzip':>9} | {'gz: pb/json':>11}")
for n in (1, 10, 100, 1000):
    lista = cursos(n)
    pb = b"".join(c.SerializeToString() for c in lista)
    js = a_json([como_dict(c) for c in lista])
    pbz, jsz = gzip.compress(pb, mtime=0), gzip.compress(js, mtime=0)
    print(f"  {n:>5} | {len(pb):>9} | {len(js):>9} | {len(pb) / len(js):>10.2f} | {len(pbz):>8} | {len(jsz):>9} |"
          f" {len(pbz) / len(jsz):>11.2f}")
