from pathlib import Path
import unittest

import yaml

from cupos.app import cupos_pb2


ROOT = Path(__file__).parents[1]


class ContractTests(unittest.TestCase):
    def test_grpc_contract_exposes_required_operations(self):
        service = cupos_pb2.DESCRIPTOR.services_by_name["Cupos"]
        self.assertEqual(
            {method.name for method in service.methods},
            {"ConsultarCurso", "ListarCursos", "OcuparCupo", "LiberarCupo"},
        )
        self.assertTrue(service.methods_by_name["ListarCursos"].server_streaming)

    def test_openapi_declares_v1_auth_and_problem_responses(self):
        contract = yaml.safe_load((ROOT / "matriculas" / "openapi.yaml").read_text(encoding="utf-8"))
        self.assertIn("bearerAuth", contract["components"]["securitySchemes"])
        self.assertIn("/v1/matriculas", contract["paths"])
        self.assertIn("Problema", contract["components"]["responses"])
        self.assertEqual(contract["components"]["responses"]["Problema"]["content"].keys(), {"application/problem+json"})
