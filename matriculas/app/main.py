import hmac
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

import grpc
import redis
import yaml
from fastapi import FastAPI, Header, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import connect
from .grpc_client import CuposClient

DB_PATH = os.getenv("MATRICULAS_DB", "/data/matriculas.db")
TOKEN_ESCRITURA = os.getenv("API_TOKEN", "desarrollo-seguro")
TOKEN_LECTURA = os.getenv("API_TOKEN_LECTURA", "solo-lectura")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "30"))
IDEMPOTENCIA_TTL = 86400
# Debe superar lo que puede tardar una matrícula (deadline gRPC de 2 s por llamada).
RESERVA_TTL = 30
EN_PROCESO = "__en_proceso__"
# Con el contenedor de Redis detenido, resolver su nombre tarda varios segundos y el timeout de
# conexión no lo cubre; tras una falla se deja de intentar Redis durante esta pausa.
REDIS_PAUSA = 15
CONTRATO = Path(__file__).resolve().parents[1] / "openapi.yaml"
RUTAS_PUBLICAS = {"/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/openapi.yaml"}
METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}
TITULOS = {
    400: "Solicitud inválida", 401: "No autenticado", 403: "Sin permiso", 404: "Recurso no encontrado",
    405: "Método no permitido", 409: "Conflicto", 422: "Solicitud inválida", 500: "Error interno",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = connect(DB_PATH)
    app.state.cupos = CuposClient()
    app.state.cache = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
        socket_timeout=0.5, socket_connect_timeout=0.5,
    )
    app.state.redis_pausa_hasta = 0.0
    yield
    app.state.cupos.close()
    app.state.cache.close()
    app.state.db.close()


app = FastAPI(title="Servicio de Matrículas", version="1.0.0", lifespan=lifespan)

# Contract-first: la API publica el openapi.yaml escrito a mano, no uno generado desde el código.
_contrato = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))
app.openapi = lambda: _contrato


class EstudianteIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr


class MatriculaIn(BaseModel):
    estudiante_id: str
    curso_id: str


class Problema(Exception):
    def __init__(self, code: int, title: str, detail: str):
        self.code, self.title, self.detail = code, title, detail


def problem(code: int, title: str, detail: str, headers: dict | None = None, **extensiones):
    return JSONResponse(
        status_code=code,
        media_type="application/problem+json",
        headers=headers,
        content={"type": f"https://httpstatuses.com/{code}", "title": title, "status": code, "detail": detail,
                 **extensiones},
    )


def titulo(code: int) -> str:
    return TITULOS.get(code) or HTTPStatus(code).phrase


@app.middleware("http")
async def bearer_auth(request: Request, call_next):
    if request.url.path in RUTAS_PUBLICAS:
        return await call_next(request)
    esquema, _, token = request.headers.get("authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not token:
        return problem(401, "No autenticado", "Se requiere el header Authorization: Bearer <token>.",
                       headers={"WWW-Authenticate": "Bearer"})
    token = token.encode()
    if hmac.compare_digest(token, TOKEN_ESCRITURA.encode()):
        return await call_next(request)
    if hmac.compare_digest(token, TOKEN_LECTURA.encode()):
        if request.method in METODOS_LECTURA:
            return await call_next(request)
        return problem(403, "Sin permiso", "El token es de solo lectura y no permite modificar recursos.")
    return problem(401, "No autenticado", "El token no es válido.",
                   headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})


@app.exception_handler(Problema)
async def problema_handler(_, exc: Problema):
    return problem(exc.code, exc.title, exc.detail)


@app.exception_handler(StarletteHTTPException)
async def http_error(_, exc: StarletteHTTPException):
    return problem(exc.status_code, titulo(exc.status_code), str(exc.detail), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc: RequestValidationError):
    errores = [{"loc": list(error["loc"]), "message": error["msg"]} for error in exc.errors()]
    return problem(422, "Solicitud inválida", "El cuerpo o sus parámetros no cumplen el contrato.", errors=errores)


@app.exception_handler(Exception)
async def error_inesperado(_, exc: Exception):
    return problem(500, "Error interno", "Ocurrió un error inesperado al procesar la solicitud.")


def en_redis(request: Request, operacion: str, *args, **kwargs):
    estado = request.app.state
    if time.monotonic() < estado.redis_pausa_hasta:
        raise redis.ConnectionError("Redis en pausa tras una falla reciente")
    try:
        return getattr(estado.cache, operacion)(*args, **kwargs)
    except redis.RedisError:
        estado.redis_pausa_hasta = time.monotonic() + REDIS_PAUSA
        raise


# Redis es una optimización: si falla, la caché se omite en vez de tumbar la API.
def cache_get(request: Request, key: str):
    try:
        return en_redis(request, "get", key)
    except redis.RedisError:
        return None


def cache_set(request: Request, key: str, ttl: int, value: str):
    try:
        en_redis(request, "setex", key, ttl, value)
    except redis.RedisError:
        pass


def cache_delete(request: Request, key: str):
    try:
        en_redis(request, "delete", key)
    except redis.RedisError:
        pass


def problema_grpc(error: grpc.RpcError, precondicion: str = "No hay cupos disponibles") -> Problema:
    # Solo NOT_FOUND y FAILED_PRECONDITION traen mensajes de negocio; los demás pueden
    # incluir direcciones internas, por eso se responde con un texto fijo.
    codigo = error.code()
    if codigo == grpc.StatusCode.NOT_FOUND:
        return Problema(404, "Curso no encontrado", error.details() or "Curso no encontrado")
    if codigo == grpc.StatusCode.FAILED_PRECONDITION:
        return Problema(409, precondicion, error.details() or precondicion)
    if codigo == grpc.StatusCode.UNAVAILABLE:
        return Problema(503, "Servicio de cupos no disponible", "Cupos no responde; reintente más tarde.")
    if codigo == grpc.StatusCode.DEADLINE_EXCEEDED:
        return Problema(504, "Tiempo de espera agotado al consultar cupos",
                        "Cupos no respondió dentro del plazo; reintente más tarde.")
    return Problema(502, "Error al comunicarse con Cupos", "Cupos respondió con un error inesperado.")


def pagina(db, tabla: str, orden: str, limit: int, offset: int, transformar=dict) -> dict:
    total = db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    filas = db.execute(f"SELECT * FROM {tabla} ORDER BY {orden} LIMIT ? OFFSET ?", (limit, offset))
    return {"items": [transformar(dict(fila)) for fila in filas], "total": total, "limit": limit, "offset": offset}


@app.get("/health", tags=["operacion"])
def health():
    return {"status": "ok"}


@app.get("/openapi.yaml", include_in_schema=False)
def contrato_yaml():
    return PlainTextResponse(CONTRATO.read_text(encoding="utf-8"), media_type="application/yaml")


@app.post("/v1/estudiantes", status_code=status.HTTP_201_CREATED, tags=["estudiantes"])
def crear_estudiante(payload: EstudianteIn, request: Request, response: Response):
    estudiante = {"id": str(uuid.uuid4()), "nombre": payload.nombre, "email": str(payload.email)}
    try:
        request.app.state.db.execute("INSERT INTO estudiantes VALUES (:id, :nombre, :email)", estudiante)
        request.app.state.db.commit()
    except sqlite3.IntegrityError:
        raise Problema(409, "Correo duplicado", "Ya existe un estudiante con ese correo.")
    response.headers["Location"] = f"/v1/estudiantes/{estudiante['id']}"
    return estudiante


@app.get("/v1/estudiantes", tags=["estudiantes"])
def listar_estudiantes(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return pagina(request.app.state.db, "estudiantes", "nombre, id", limit, offset)


@app.get("/v1/estudiantes/{estudiante_id}", tags=["estudiantes"])
def consultar_estudiante(estudiante_id: str, request: Request):
    row = request.app.state.db.execute("SELECT * FROM estudiantes WHERE id=?", (estudiante_id,)).fetchone()
    if not row:
        raise Problema(404, "Estudiante no encontrado", "No existe un estudiante con ese id.")
    return dict(row)


def curso_disponibilidad(request: Request, curso_id: str):
    key = f"curso:{curso_id}"
    saved = cache_get(request, key)
    if saved:
        return json.loads(saved)
    curso = request.app.state.cupos.consultar(curso_id)
    result = {"id": curso.id, "nombre": curso.nombre, "cupos_disponibles": curso.cupos_disponibles}
    cache_set(request, key, CACHE_TTL, json.dumps(result))
    return result


def representacion_matricula(matricula: dict) -> dict:
    """Representación REST con acciones permitidas según el estado (HATEOAS)."""
    resultado = dict(matricula)
    base = f"/v1/matriculas/{resultado['id']}"
    links = {"self": {"href": base, "method": "GET"}}
    if resultado["estado"] == "activa":
        links["revertir"] = {"href": f"{base}/revertir", "method": "POST"}
    resultado["_links"] = links
    return resultado


@app.get("/v1/cursos/{curso_id}", tags=["cursos"])
def consultar_curso(curso_id: str, request: Request):
    try:
        return curso_disponibilidad(request, curso_id)
    except grpc.RpcError as error:
        raise problema_grpc(error)


def reservar_idempotencia(request: Request, clave: str) -> dict | None:
    """Devuelve la respuesta ya guardada para la clave, o None si esta petición la reservó."""
    key = f"idempotencia:{clave}"
    try:
        # SET NX es atómico: de dos reintentos simultáneos, solo uno procesa la matrícula.
        if en_redis(request, "set", key, EN_PROCESO, nx=True, ex=RESERVA_TTL):
            return None
        guardada = en_redis(request, "get", key)
    except redis.RedisError:
        raise Problema(503, "Idempotencia no disponible",
                       "No se puede garantizar Idempotency-Key en este momento; reintente más tarde.")
    if guardada is None or guardada == EN_PROCESO:
        raise Problema(409, "Solicitud en proceso", "Ya se está procesando una matrícula con esta Idempotency-Key.")
    return json.loads(guardada)


def registrar_matricula(request: Request, payload: MatriculaIn) -> dict:
    db = request.app.state.db
    if not db.execute("SELECT 1 FROM estudiantes WHERE id=?", (payload.estudiante_id,)).fetchone():
        raise Problema(404, "Estudiante no encontrado", "No existe un estudiante con ese id.")
    duplicada = Problema(409, "Matrícula duplicada", "El estudiante ya tiene una matrícula activa en este curso.")
    if db.execute("SELECT 1 FROM matriculas WHERE estudiante_id=? AND curso_id=? AND estado='activa'",
                  (payload.estudiante_id, payload.curso_id)).fetchone():
        raise duplicada
    try:
        curso = request.app.state.cupos.ocupar(payload.curso_id)
    except grpc.RpcError as error:
        raise problema_grpc(error)
    matricula = {"id": str(uuid.uuid4()), "estudiante_id": payload.estudiante_id, "curso_id": payload.curso_id,
                 "estado": "activa", "creada_en": datetime.now(timezone.utc).isoformat()}
    try:
        db.execute("INSERT INTO matriculas VALUES (:id, :estudiante_id, :curso_id, :estado, :creada_en)", matricula)
        db.commit()
    except sqlite3.IntegrityError:
        # Otra petición concurrente ganó la carrera por la misma matrícula: se devuelve el cupo recién ocupado.
        db.rollback()
        try:
            request.app.state.cupos.liberar(payload.curso_id)
        except grpc.RpcError:
            pass
        raise duplicada
    cache_delete(request, f"curso:{curso.id}")
    return matricula


@app.post("/v1/matriculas", status_code=status.HTTP_201_CREATED, tags=["matriculas"])
def crear_matricula(payload: MatriculaIn, request: Request, response: Response,
                    idempotency_key: str | None = Header(default=None, max_length=128)):
    if idempotency_key:
        previa = reservar_idempotencia(request, idempotency_key)
        if previa is not None:
            return JSONResponse(status_code=200, content=previa, headers={
                "Location": previa["_links"]["self"]["href"], "Idempotent-Replay": "true"})
    try:
        representacion = representacion_matricula(registrar_matricula(request, payload))
    except Exception:
        if idempotency_key:
            cache_delete(request, f"idempotencia:{idempotency_key}")
        raise
    if idempotency_key:
        cache_set(request, f"idempotencia:{idempotency_key}", IDEMPOTENCIA_TTL, json.dumps(representacion))
    response.headers["Location"] = representacion["_links"]["self"]["href"]
    return representacion


@app.get("/v1/matriculas", tags=["matriculas"])
def listar_matriculas(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return pagina(request.app.state.db, "matriculas", "creada_en DESC, id", limit, offset, representacion_matricula)


@app.get("/v1/matriculas/{matricula_id}", tags=["matriculas"])
def consultar_matricula(matricula_id: str, request: Request):
    row = request.app.state.db.execute("SELECT * FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
    if not row:
        raise Problema(404, "Matrícula no encontrada", "No existe una matrícula con ese id.")
    return representacion_matricula(dict(row))


@app.post("/v1/matriculas/{matricula_id}/revertir", tags=["matriculas"])
def revertir_matricula(matricula_id: str, request: Request):
    db = request.app.state.db
    row = db.execute("SELECT * FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
    if not row:
        raise Problema(404, "Matrícula no encontrada", "No existe una matrícula con ese id.")
    # Se marca primero como revertida con un UPDATE condicional: si dos reversiones llegan a la vez,
    # solo una cambia la fila y libera el cupo.
    cambio = db.execute("UPDATE matriculas SET estado='revertida' WHERE id=? AND estado='activa'", (matricula_id,))
    db.commit()
    if cambio.rowcount == 0:
        raise Problema(409, "Matrícula ya revertida", "La matrícula ya fue revertida.")
    try:
        request.app.state.cupos.liberar(row["curso_id"])
    except grpc.RpcError as error:
        db.execute("UPDATE matriculas SET estado='activa' WHERE id=?", (matricula_id,))
        db.commit()
        raise problema_grpc(error, precondicion="El curso no tiene cupos ocupados que liberar")
    cache_delete(request, f"curso:{row['curso_id']}")
    return representacion_matricula({**dict(row), "estado": "revertida"})
