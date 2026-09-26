"""Genera los stubs Python de cupos/cupos.proto (lo generado no se versiona)."""
import re
from pathlib import Path

import grpc_tools
from grpc_tools import protoc

RAIZ = Path(__file__).resolve().parents[1]
PROTO = RAIZ / "cupos" / "cupos.proto"
DESTINOS = (RAIZ / "cupos" / "app", RAIZ / "matriculas" / "app")


def generar():
    includes = Path(grpc_tools.__file__).parent / "_proto"
    for destino in DESTINOS:
        codigo = protoc.main([
            "protoc", f"-I{PROTO.parent}", f"-I{includes}",
            f"--python_out={destino}", f"--grpc_python_out={destino}", str(PROTO),
        ])
        if codigo != 0:
            raise RuntimeError(f"protoc falló generando stubs en {destino}")
        stub = destino / "cupos_pb2_grpc.py"
        # protoc emite un import absoluto; los servicios lo usan como paquete.
        texto = re.sub(r"^import cupos_pb2", "from . import cupos_pb2", stub.read_text(encoding="utf-8"), flags=re.M)
        stub.write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    generar()
