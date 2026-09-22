import os
import grpc

from . import cupos_pb2, cupos_pb2_grpc


class CuposClient:
    """Un único canal reutilizable para todas las solicitudes HTTP."""
    def __init__(self):
        self.channel = grpc.insecure_channel(os.getenv("CUPOS_GRPC_TARGET", "localhost:50051"))
        self.stub = cupos_pb2_grpc.CuposStub(self.channel)
        self.timeout = float(os.getenv("GRPC_TIMEOUT_SECONDS", "2"))

    def consultar(self, curso_id):
        return self.stub.ConsultarCurso(cupos_pb2.ConsultarCursoRequest(curso_id=curso_id), timeout=self.timeout)

    def ocupar(self, curso_id):
        return self.stub.OcuparCupo(cupos_pb2.ModificarCupoRequest(curso_id=curso_id), timeout=self.timeout)

    def liberar(self, curso_id):
        return self.stub.LiberarCupo(cupos_pb2.ModificarCupoRequest(curso_id=curso_id), timeout=self.timeout)

    def close(self):
        self.channel.close()
