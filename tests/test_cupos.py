import tempfile
import unittest

import grpc

from cupos.app import cupos_pb2
from cupos.app.server import CuposService


class Context:
    def abort(self, code, details):
        raise RuntimeError((code, details))


class CuposTests(unittest.TestCase):
    def test_ocupar_y_liberar_cupo(self):
        with tempfile.TemporaryDirectory() as directory:
            service = CuposService(f"{directory}/cupos.db")
            request = cupos_pb2.ModificarCupoRequest(curso_id="API-201")
            self.assertEqual(service.OcuparCupo(request, Context()).cupos_disponibles, 0)
            with self.assertRaisesRegex(RuntimeError, "FAILED_PRECONDITION"):
                service.OcuparCupo(request, Context())
            self.assertEqual(service.LiberarCupo(request, Context()).cupos_disponibles, 1)
            service.db.close()

    def test_curso_inexistente(self):
        with tempfile.TemporaryDirectory() as directory:
            service = CuposService(f"{directory}/cupos.db")
            with self.assertRaisesRegex(RuntimeError, "NOT_FOUND"):
                service.ConsultarCurso(cupos_pb2.ConsultarCursoRequest(curso_id="NOPE"), Context())
            service.db.close()
