import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import grpc
import redis
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, EmailStr, Field

from .database import connect
from .grpc_client import CuposClient

DB_PATH = os.getenv("MATRICULAS_DB", "/data/matriculas.db")
TOKEN = os.getenv("API_TOKEN", "desarrollo-seguro")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "30"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = connect(DB_PATH)
    app.state.cupos = CuposClient()
    app.state.cache = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    yield
    app.state.cupos.close()
    app.state.db.close()


app = FastAPI(title="Servicio de Matrículas", version="1.0.0", lifespan=lifespan)


def custom_openapi():
    """Mantiene Swagger sincronizado con el contrato de autenticación Bearer."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["bearerAuth"] = {
        "type": "http", "scheme": "bearer", "bearerFormat": "JWT"
    }
    schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


class EstudianteIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr


class MatriculaIn(BaseModel):
    estudiante_id: str
    curso_id: str


def problem(code: int, title: str, detail: str):
    return JSONResponse(
        status_code=code,
        media_type="application/problem+json",
        content={"type": f"https://httpstatuses.com/{code}", "title": title, "status": code, "detail": detail},
    )


@app.middleware("http")
async def bearer_auth(request: Request, call_next):
    if request.url.path in {"/health", "/docs", "/openapi.json"}:
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return problem(401, "No autenticado", "Se requiere un token Bearer.")
    if header.removeprefix("Bearer ") != TOKEN:
        return problem(403, "No autorizado", "El token no tiene permisos para este recurso.")
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return problem(exc.status_code, "Solicitud inválida", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc: RequestValidationError):
    response = problem(422, "Solicitud inválida", "El cuerpo o sus parámetros no cumplen el contrato.")
    # RFC 9457 permite extensiones; se entrega ubicación y mensaje sin detalles internos.
    response.body = json.dumps({
        "type": "https://httpstatuses.com/422",
        "title": "Solicitud inválida",
        "status": 422,
        "detail": "El cuerpo o sus parámetros no cumplen el contrato.",
        "errors": [{"loc": list(error["loc"]), "message": error["msg"]} for error in exc.errors()],
    }).encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


@app.get("/health", tags=["operacion"])
def health():
    return {"status": "ok"}


@app.post("/v1/estudiantes", status_code=status.HTTP_201_CREATED, tags=["estudiantes"])
def crear_estudiante(payload: EstudianteIn, request: Request):
    estudiante = {"id": str(uuid.uuid4()), "nombre": payload.nombre, "email": str(payload.email)}
    try:
        request.app.state.db.execute("INSERT INTO estudiantes VALUES (:id, :nombre, :email)", estudiante)
        request.app.state.db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ya existe un estudiante con ese correo.")
    return estudiante


@app.get("/v1/estudiantes", tags=["estudiantes"])
def listar_estudiantes(request: Request):
    return [dict(row) for row in request.app.state.db.execute("SELECT * FROM estudiantes ORDER BY nombre")]


@app.get("/v1/estudiantes/{estudiante_id}", tags=["estudiantes"])
def consultar_estudiante(estudiante_id: str, request: Request):
    row = request.app.state.db.execute("SELECT * FROM estudiantes WHERE id=?", (estudiante_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Estudiante no encontrado.")
    return dict(row)


def grpc_problem(error: grpc.RpcError):
    mapping = {
        grpc.StatusCode.UNAVAILABLE: (503, "Servicio de cupos no disponible"),
        grpc.StatusCode.DEADLINE_EXCEEDED: (504, "Tiempo de espera agotado al consultar cupos"),
        grpc.StatusCode.NOT_FOUND: (404, "Curso no encontrado"),
        grpc.StatusCode.FAILED_PRECONDITION: (409, "No hay cupos disponibles"),
    }
    code, title = mapping.get(error.code(), (502, "Error al comunicarse con Cupos"))
    return problem(code, title, error.details() or title)


def curso_disponibilidad(request: Request, curso_id: str):
    key = f"curso:{curso_id}"
    saved = request.app.state.cache.get(key)
    if saved:
        return json.loads(saved)
    curso = request.app.state.cupos.consultar(curso_id)
    result = {"id": curso.id, "nombre": curso.nombre, "cupos_disponibles": curso.cupos_disponibles}
    request.app.state.cache.setex(key, CACHE_TTL, json.dumps(result))
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
        return grpc_problem(error)


@app.post("/v1/matriculas", status_code=status.HTTP_201_CREATED, tags=["matriculas"])
def crear_matricula(payload: MatriculaIn, request: Request, idempotency_key: str | None = Header(default=None)):
    db = request.app.state.db
    now = int(time.time())
    if idempotency_key:
        saved = request.app.state.cache.get(f"idempotencia:{idempotency_key}")
        if saved:
            return JSONResponse(status_code=200, content=json.loads(saved))
    if not db.execute("SELECT 1 FROM estudiantes WHERE id=?", (payload.estudiante_id,)).fetchone():
        raise HTTPException(404, "Estudiante no encontrado.")
    try:
        curso_disponibilidad(request, payload.curso_id)
        curso = request.app.state.cupos.ocupar(payload.curso_id)
    except grpc.RpcError as error:
        return grpc_problem(error)
    matricula = {"id": str(uuid.uuid4()), "estudiante_id": payload.estudiante_id, "curso_id": payload.curso_id,
                 "estado": "activa", "creada_en": datetime.now(timezone.utc).isoformat()}
    db.execute("INSERT INTO matriculas VALUES (:id, :estudiante_id, :curso_id, :estado, :creada_en)", matricula)
    if idempotency_key:
        request.app.state.cache.setex(f"idempotencia:{idempotency_key}", 86400, json.dumps(representacion_matricula(matricula)))
    db.commit()
    request.app.state.cache.delete(f"curso:{curso.id}")
    return representacion_matricula(matricula)


@app.get("/v1/matriculas", tags=["matriculas"])
def listar_matriculas(request: Request):
    return [representacion_matricula(dict(row)) for row in request.app.state.db.execute("SELECT * FROM matriculas ORDER BY creada_en DESC")]


@app.get("/v1/matriculas/{matricula_id}", tags=["matriculas"])
def consultar_matricula(matricula_id: str, request: Request):
    row = request.app.state.db.execute("SELECT * FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Matrícula no encontrada.")
    return representacion_matricula(dict(row))


@app.post("/v1/matriculas/{matricula_id}/revertir", tags=["matriculas"])
def revertir_matricula(matricula_id: str, request: Request):
    db = request.app.state.db
    row = db.execute("SELECT * FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Matrícula no encontrada.")
    if row["estado"] == "revertida":
        raise HTTPException(409, "La matrícula ya fue revertida.")
    try:
        request.app.state.cupos.liberar(row["curso_id"])
    except grpc.RpcError as error:
        return grpc_problem(error)
    db.execute("UPDATE matriculas SET estado='revertida' WHERE id=?", (matricula_id,))
    db.commit()
    request.app.state.cache.delete(f"curso:{row['curso_id']}")
    return representacion_matricula({**dict(row), "estado": "revertida"})
