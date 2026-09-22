import os
import threading
from concurrent import futures

import grpc

from . import cupos_pb2, cupos_pb2_grpc
from .database import connect, seed


class CuposService(cupos_pb2_grpc.CuposServicer):
    def __init__(self, database_path: str):
        self.db = connect(database_path)
        seed(self.db)
        self.lock = threading.Lock()

    @staticmethod
    def _curso(row):
        return cupos_pb2.Curso(
            id=row["id"], nombre=row["nombre"], cupos_totales=row["cupos_totales"],
            cupos_disponibles=row["cupos_disponibles"],
        )

    def ConsultarCurso(self, request, context):
        row = self.db.execute("SELECT * FROM cursos WHERE id = ?", (request.curso_id,)).fetchone()
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "Curso no encontrado")
        return self._curso(row)

    def ListarCursos(self, request, context):
        for row in self.db.execute("SELECT * FROM cursos ORDER BY id"):
            yield self._curso(row)

    def OcuparCupo(self, request, context):
        with self.lock:
            row = self.db.execute("SELECT * FROM cursos WHERE id = ?", (request.curso_id,)).fetchone()
            if not row:
                context.abort(grpc.StatusCode.NOT_FOUND, "Curso no encontrado")
            if row["cupos_disponibles"] == 0:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "No hay cupos disponibles")
            self.db.execute("UPDATE cursos SET cupos_disponibles = cupos_disponibles - 1 WHERE id = ?", (request.curso_id,))
            self.db.commit()
            return self.ConsultarCurso(request, context)

    def LiberarCupo(self, request, context):
        with self.lock:
            row = self.db.execute("SELECT * FROM cursos WHERE id = ?", (request.curso_id,)).fetchone()
            if not row:
                context.abort(grpc.StatusCode.NOT_FOUND, "Curso no encontrado")
            if row["cupos_disponibles"] >= row["cupos_totales"]:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Todos los cupos ya estan liberados")
            self.db.execute("UPDATE cursos SET cupos_disponibles = cupos_disponibles + 1 WHERE id = ?", (request.curso_id,))
            self.db.commit()
            return self.ConsultarCurso(request, context)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cupos_pb2_grpc.add_CuposServicer_to_server(
        CuposService(os.getenv("CUPOS_DB", "/data/cupos.db")), server
    )
    server.add_insecure_port("[::]:" + os.getenv("GRPC_PORT", "50051"))
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
