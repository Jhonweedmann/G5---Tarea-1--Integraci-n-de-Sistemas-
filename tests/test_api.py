"""Pruebas de contrato: la API real contra openapi.yaml, con Cupos y Redis simulados."""
import tempfile
import unittest
from pathlib import Path

import grpc
import redis
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from scripts.generar_stubs import generar

generar()
from matriculas.app import main  # noqa: E402
from matriculas.app.cupos_pb2 import Curso  # noqa: E402

SPEC = yaml.safe_load((Path(__file__).parents[1] / "matriculas" / "openapi.yaml").read_text(encoding="utf-8"))
ESCRITURA = {"Authorization": "Bearer desarrollo-seguro"}
LECTURA = {"Authorization": "Bearer solo-lectura"}


class FallaRpc(grpc.RpcError):
    def __init__(self, codigo, detalle=""):
        self._codigo, self._detalle = codigo, detalle

    def code(self):
        return self._codigo

    def details(self):
        return self._detalle


class CuposFalso:
    def __init__(self):
        self.cursos = {"ARQ-101": ["Arquitectura de Sistemas", 2, 2], "API-201": ["Integracion de APIs", 1, 1]}
        self.falla = None
        self.llamadas = 0

    def _curso(self, curso_id):
        self.llamadas += 1
        if self.falla:
            raise self.falla
        if curso_id not in self.cursos:
            raise FallaRpc(grpc.StatusCode.NOT_FOUND, "Curso no encontrado")
        return self.cursos[curso_id]

    def consultar(self, curso_id):
        nombre, totales, disponibles = self._curso(curso_id)
        return Curso(id=curso_id, nombre=nombre, cupos_totales=totales, cupos_disponibles=disponibles)

    def ocupar(self, curso_id):
        curso = self._curso(curso_id)
        if curso[2] == 0:
            raise FallaRpc(grpc.StatusCode.FAILED_PRECONDITION, "No hay cupos disponibles")
        curso[2] -= 1
        return self.consultar(curso_id)

    def liberar(self, curso_id):
        curso = self._curso(curso_id)
        if curso[2] >= curso[1]:
            raise FallaRpc(grpc.StatusCode.FAILED_PRECONDITION, "Todos los cupos ya estan liberados")
        curso[2] += 1
        return self.consultar(curso_id)

    def close(self):
        pass


class RedisFalso:
    def __init__(self):
        self.datos = {}
        self.caido = False
        self.intentos = 0

    def _verificar(self):
        self.intentos += 1
        if self.caido:
            raise redis.ConnectionError("Redis caído")

    def get(self, key):
        self._verificar()
        return self.datos.get(key)

    def setex(self, key, ttl, value):
        self._verificar()
        self.datos[key] = value

    def set(self, key, value, nx=False, ex=None):
        self._verificar()
        if nx and key in self.datos:
            return None
        self.datos[key] = value
        return True

    def delete(self, key):
        self._verificar()
        self.datos.pop(key, None)

    def close(self):
        pass


class ApiContratoTests(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        main.DB_PATH = f"{self.directorio.name}/matriculas.db"
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.cupos = main.app.state.cupos = CuposFalso()
        self.cache = main.app.state.cache = RedisFalso()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directorio.cleanup()

    def cumple_contrato(self, respuesta, ruta, metodo):
        """Verifica que el código esté declarado y que el cuerpo cumpla el esquema del contrato."""
        declaradas = SPEC["paths"][ruta][metodo]["responses"]
        codigo = str(respuesta.status_code)
        self.assertIn(codigo, declaradas, f"{metodo.upper()} {ruta} devolvió {codigo}, no declarado: {respuesta.text}")
        declarada = declaradas[codigo]
        if "$ref" in declarada:
            declarada = SPEC["components"]["responses"][declarada["$ref"].rsplit("/", 1)[-1]]
        tipo = respuesta.headers["content-type"].split(";")[0]
        self.assertIn(tipo, declarada["content"])
        Draft202012Validator({**SPEC, **declarada["content"][tipo]["schema"]}).validate(respuesta.json())
        for cabecera in declarada.get("headers", {}):
            if cabecera != "Idempotent-Replay" or respuesta.status_code == 200:
                self.assertIn(cabecera, respuesta.headers)
        return respuesta.json()

    def crear_estudiante(self, email="ana@example.com"):
        r = self.client.post("/v1/estudiantes", json={"nombre": "Ana Perez", "email": email}, headers=ESCRITURA)
        return self.cumple_contrato(r, "/v1/estudiantes", "post")

    def matricular(self, estudiante_id, curso_id="ARQ-101", headers=None):
        return self.client.post("/v1/matriculas", json={"estudiante_id": estudiante_id, "curso_id": curso_id},
                                headers={**ESCRITURA, **(headers or {})})

    # --- Autenticación (T6) ---

    def test_sin_token_responde_401_con_www_authenticate(self):
        r = self.client.get("/v1/estudiantes")
        self.cumple_contrato(r, "/v1/estudiantes", "get")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers["www-authenticate"], "Bearer")

    def test_token_invalido_responde_401_no_403(self):
        r = self.client.get("/v1/estudiantes", headers={"Authorization": "Bearer inventado"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("invalid_token", r.headers["www-authenticate"])

    def test_token_de_lectura_lee_pero_no_escribe(self):
        self.assertEqual(self.client.get("/v1/estudiantes", headers=LECTURA).status_code, 200)
        r = self.client.post("/v1/estudiantes", json={"nombre": "Ana", "email": "a@b.cl"}, headers=LECTURA)
        self.cumple_contrato(r, "/v1/estudiantes", "post")
        self.assertEqual(r.status_code, 403)

    # --- Estudiantes y colecciones ---

    def test_crear_estudiante_devuelve_location_y_rechaza_correo_repetido(self):
        estudiante = self.crear_estudiante()
        r = self.client.get(f"/v1/estudiantes/{estudiante['id']}", headers=ESCRITURA)
        self.assertEqual(self.cumple_contrato(r, "/v1/estudiantes/{estudiante_id}", "get"), estudiante)
        r = self.client.post("/v1/estudiantes", json={"nombre": "Otra", "email": "ana@example.com"}, headers=ESCRITURA)
        self.cumple_contrato(r, "/v1/estudiantes", "post")
        self.assertEqual(r.status_code, 409)

    def test_listado_paginado(self):
        for i in range(3):
            self.crear_estudiante(f"e{i}@example.com")
        r = self.client.get("/v1/estudiantes?limit=2&offset=1", headers=ESCRITURA)
        pagina = self.cumple_contrato(r, "/v1/estudiantes", "get")
        self.assertEqual((len(pagina["items"]), pagina["total"]), (2, 3))
        r = self.client.get("/v1/estudiantes?limit=0", headers=ESCRITURA)
        self.assertEqual(self.cumple_contrato(r, "/v1/estudiantes", "get")["status"], 422)

    def test_cuerpo_invalido_responde_422_problem_json(self):
        r = self.client.post("/v1/estudiantes", json={"nombre": "A"}, headers=ESCRITURA)
        cuerpo = self.cumple_contrato(r, "/v1/estudiantes", "post")
        self.assertEqual(r.status_code, 422)
        self.assertTrue(cuerpo["errors"])

    # --- Matrículas, HATEOAS e integración con Cupos ---

    def test_flujo_matricular_y_revertir(self):
        estudiante = self.crear_estudiante()
        r = self.matricular(estudiante["id"])
        matricula = self.cumple_contrato(r, "/v1/matriculas", "post")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.headers["location"], f"/v1/matriculas/{matricula['id']}")
        self.assertIn("revertir", matricula["_links"])
        self.assertEqual(self.cupos.cursos["ARQ-101"][2], 1)

        r = self.client.post(f"/v1/matriculas/{matricula['id']}/revertir", headers=ESCRITURA)
        revertida = self.cumple_contrato(r, "/v1/matriculas/{matricula_id}/revertir", "post")
        self.assertEqual(revertida["estado"], "revertida")
        self.assertNotIn("revertir", revertida["_links"])
        self.assertEqual(self.cupos.cursos["ARQ-101"][2], 2)

        r = self.client.post(f"/v1/matriculas/{matricula['id']}/revertir", headers=ESCRITURA)
        self.cumple_contrato(r, "/v1/matriculas/{matricula_id}/revertir", "post")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.cupos.cursos["ARQ-101"][2], 2)

        r = self.client.get("/v1/matriculas", headers=ESCRITURA)
        self.assertEqual(self.cumple_contrato(r, "/v1/matriculas", "get")["total"], 1)

    def test_sin_cupos_responde_409(self):
        self.matricular(self.crear_estudiante("a@example.com")["id"], "API-201")
        r = self.matricular(self.crear_estudiante("b@example.com")["id"], "API-201")
        self.assertEqual(self.cumple_contrato(r, "/v1/matriculas", "post")["title"], "No hay cupos disponibles")
        self.assertEqual(r.status_code, 409)

    def test_matricula_activa_duplicada_no_ocupa_otro_cupo(self):
        estudiante = self.crear_estudiante()
        self.matricular(estudiante["id"])
        r = self.matricular(estudiante["id"])
        self.cumple_contrato(r, "/v1/matriculas", "post")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.cupos.cursos["ARQ-101"][2], 1)

    def test_estudiante_y_curso_inexistentes_responden_404(self):
        r = self.matricular("no-existe")
        self.cumple_contrato(r, "/v1/matriculas", "post")
        self.assertEqual(r.status_code, 404)
        r = self.matricular(self.crear_estudiante()["id"], "NOPE")
        self.cumple_contrato(r, "/v1/matriculas", "post")
        self.assertEqual(r.status_code, 404)

    # --- Idempotencia (O2) ---

    def test_reintento_con_misma_clave_devuelve_la_original_sin_ocupar_otro_cupo(self):
        estudiante = self.crear_estudiante()
        primera = self.matricular(estudiante["id"], headers={"Idempotency-Key": "k-1"})
        segunda = self.matricular(estudiante["id"], headers={"Idempotency-Key": "k-1"})
        self.assertEqual((primera.status_code, segunda.status_code), (201, 200))
        self.assertEqual(self.cumple_contrato(segunda, "/v1/matriculas", "post"), primera.json())
        self.assertEqual(segunda.headers["idempotent-replay"], "true")
        self.assertEqual(self.cupos.cursos["ARQ-101"][2], 1)

    def test_clave_en_proceso_responde_409(self):
        self.cache.datos["idempotencia:k-2"] = main.EN_PROCESO
        r = self.matricular(self.crear_estudiante()["id"], headers={"Idempotency-Key": "k-2"})
        self.cumple_contrato(r, "/v1/matriculas", "post")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.cupos.llamadas, 0)

    def test_si_la_matricula_falla_la_clave_queda_libre_para_reintentar(self):
        estudiante = self.crear_estudiante()
        self.cupos.falla = FallaRpc(grpc.StatusCode.UNAVAILABLE)
        self.assertEqual(self.matricular(estudiante["id"], headers={"Idempotency-Key": "k-3"}).status_code, 503)
        self.cupos.falla = None
        self.assertEqual(self.matricular(estudiante["id"], headers={"Idempotency-Key": "k-3"}).status_code, 201)

    # --- Fallas de dependencias (T7) ---

    def test_fallas_de_cupos_se_traducen_sin_filtrar_detalles_internos(self):
        estudiante = self.crear_estudiante()
        casos = {grpc.StatusCode.UNAVAILABLE: 503, grpc.StatusCode.DEADLINE_EXCEEDED: 504,
                 grpc.StatusCode.INTERNAL: 502}
        for codigo, esperado in casos.items():
            self.cupos.falla = FallaRpc(codigo, "failed to connect to ipv4:172.18.0.2:50051")
            for r, ruta in ((self.matricular(estudiante["id"]), "/v1/matriculas"),
                            (self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA), "/v1/cursos/{curso_id}")):
                cuerpo = self.cumple_contrato(r, ruta, "post" if ruta == "/v1/matriculas" else "get")
                self.assertEqual(r.status_code, esperado)
                self.assertNotIn("172.18", cuerpo["detail"])

    def test_redis_caido_no_tumba_la_api(self):
        estudiante = self.crear_estudiante()
        self.cache.caido = True
        r = self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA)
        self.assertEqual(self.cumple_contrato(r, "/v1/cursos/{curso_id}", "get")["cupos_disponibles"], 2)
        r = self.matricular(estudiante["id"], headers={"Idempotency-Key": "k-4"})
        self.cumple_contrato(r, "/v1/matriculas", "post")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.cupos.cursos["ARQ-101"][2], 2)
        self.assertEqual(self.matricular(estudiante["id"]).status_code, 201)

    def test_tras_una_falla_de_redis_no_se_reintenta_durante_la_pausa(self):
        self.cache.caido = True
        self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA)
        intentos = self.cache.intentos
        for _ in range(3):
            self.assertEqual(self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA).status_code, 200)
        self.assertEqual(self.cache.intentos, intentos)

        self.cache.caido = False
        main.app.state.redis_pausa_hasta = 0.0
        self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA)
        self.assertIn("curso:ARQ-101", self.cache.datos)

    def test_cache_se_invalida_al_ocupar(self):
        self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA)
        self.assertIn("curso:ARQ-101", self.cache.datos)
        self.matricular(self.crear_estudiante()["id"])
        self.assertNotIn("curso:ARQ-101", self.cache.datos)
        r = self.client.get("/v1/cursos/ARQ-101", headers=ESCRITURA)
        self.assertEqual(r.json()["cupos_disponibles"], 1)

    # --- Formato uniforme de errores ---

    def test_ruta_y_metodo_inexistentes_responden_problem_json(self):
        r = self.client.get("/v1/no-existe", headers=ESCRITURA)
        self.assertEqual((r.status_code, r.headers["content-type"]), (404, "application/problem+json"))
        r = self.client.delete("/v1/estudiantes", headers=ESCRITURA)
        self.assertEqual((r.status_code, r.headers["content-type"]), (405, "application/problem+json"))

    def test_error_inesperado_responde_500_problem_json_sin_traza(self):
        self.cupos.falla = RuntimeError("detalle interno que no debe salir")
        r = TestClient(main.app, raise_server_exceptions=False).get("/v1/cursos/ARQ-101", headers=ESCRITURA)
        self.assertEqual((r.status_code, r.headers["content-type"]), (500, "application/problem+json"))
        self.assertNotIn("detalle interno", r.text)

    def test_la_api_publica_el_contrato_escrito_a_mano(self):
        self.assertEqual(self.client.get("/openapi.json").json(), SPEC)


if __name__ == "__main__":
    unittest.main()
