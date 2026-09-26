# Forma K — Cursos y Matrículas

Sistema distribuido de ejemplo para administrar estudiantes, matrículas y cupos. `matriculas` expone una API REST y delega la disponibilidad a `cupos` mediante gRPC. Las bases de datos están deliberadamente separadas.

## Ejecutar

```powershell
docker compose up --build
```

La API queda disponible en `http://localhost:8000`; la documentación interactiva está en `/docs` y el contrato en `/openapi.yaml` (es el mismo `matriculas/openapi.yaml`, no uno generado desde el código).

Tokens de desarrollo (`Authorization: Bearer <token>`):

| Token | Permite | Sin token o token desconocido | Token válido sin permiso |
|---|---|---|---|
| `desarrollo-seguro` | lectura y escritura | 401 | — |
| `solo-lectura` | solo `GET` | 401 | 403 |

La composición levanta también Redis, utilizado por las opciones de caché e idempotencia. Solo la API publica un puerto (8000): Cupos y Redis quedan accesibles únicamente dentro de la red de Compose.

```powershell
$headers = @{ Authorization = 'Bearer desarrollo-seguro' }
$e = Invoke-RestMethod http://localhost:8000/v1/estudiantes -Method Post -Headers $headers -ContentType application/json -Body '{"nombre":"Ana Perez","email":"ana@example.com"}'
$m = Invoke-RestMethod http://localhost:8000/v1/matriculas -Method Post -Headers $headers -ContentType application/json -Body "{\"estudiante_id\":\"$($e.id)\",\"curso_id\":\"ARQ-101\"}"
Invoke-RestMethod "http://localhost:8000/v1/matriculas/$($m.id)/revertir" -Method Post -Headers $headers
```

Para demostrar resiliencia, ejecute `docker compose stop cupos` y consulte o cree una matrícula. Durante los primeros ~15 s el canal gRPC sigue intentando conectar y cada llamada agota el deadline de 2 s, por lo que la API responde `504`. Luego el canal marca a Cupos como caído y la API responde `503` en ~10 ms. Al volver Cupos responde `200`. Ambos casos usan `application/problem+json`.

Si Redis cae, la consulta de cursos sigue funcionando sin caché. Un `POST /v1/matriculas` con `Idempotency-Key` responde `503`, porque sin Redis no se puede garantizar la idempotencia; sin la clave, la matrícula se procesa normalmente.

Segundo cliente gRPC (Node.js, O5), ejecutado dentro de la red de Compose:

```powershell
docker compose --profile demo run --rm cupos-node-client
```

## Contratos y decisiones

- gRPC: [cupos.proto](cupos/cupos.proto)
- REST: [openapi.yaml](matriculas/openapi.yaml)
- Decisiones: [ADR](docs/adr)
- Informe: fuente LaTeX en [informe.tex](docs/informe.tex), compilado en [Informe-Forma-K.pdf](docs/Informe-Forma-K.pdf)
- Experimentos: [serialización](docs/experimento_serializacion.py) y [resiliencia](docs/experimento_resiliencia.py), con datos crudos en [docs/resultados](docs/resultados)
- Guion: [guion-video.md](docs/guion-video.md)

## Idempotencia y caché

`POST /v1/matriculas` acepta `Idempotency-Key`; una repetición durante 24 horas devuelve la respuesta guardada en Redis y no ocupa otro cupo. La consulta de curso usa cache-aside en Redis con TTL corto y se invalida al ocupar o liberar.

Las representaciones de matrículas incluyen `_links`: una matrícula activa expone la acción `revertir`; una revertida no. Esto evita ofrecer una transición inválida al cliente.

## Experimentos

```powershell
.\.venv\Scripts\python docs\experimento_serializacion.py
.\.venv\Scripts\python docs\experimento_resiliencia.py --repeticiones 5 --duracion 35
```

El primero no necesita Docker. El segundo necesita el sistema levantado: detiene y reinicia el contenedor de Cupos en cada repetición. Resultados en §10 del informe:

- **Serialización:** un `Curso` pesa 39 bytes en protobuf y 94 en JSON; con gzip la ventaja baja de 0,40 a 0,73–0,85.
- **Resiliencia:** con Cupos detenido la API responde 504 durante 20,0 s y luego 503 en unos 9 ms.

## Pruebas

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests -v
```

`tests/test_api.py` son pruebas de contrato: ejecutan la API real (con Cupos y Redis simulados) y validan cada respuesta contra `matriculas/openapi.yaml`, tanto el código de estado declarado como el esquema con `additionalProperties: false`.

Los stubs Python de gRPC (`cupos_pb2*.py`) no se versionan. Los Dockerfiles los generan desde `cupos/cupos.proto` y, en local, las pruebas los regeneran automáticamente (o manualmente con `python scripts/generar_stubs.py`).

## Uso de IA

Se usó asistencia de IA para estructurar código, contratos y documentación. El equipo debe revisar el código generado, ejecutar pruebas y explicar las decisiones y resultados del experimento.
