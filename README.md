# Forma K — Cursos y Matrículas

Sistema distribuido de ejemplo para administrar estudiantes, matrículas y cupos. `matriculas` expone una API REST y delega la disponibilidad a `cupos` mediante gRPC. Las bases de datos están deliberadamente separadas.

## Ejecutar

```powershell
docker compose up --build
```

La API queda disponible en `http://localhost:8000`; la documentación interactiva está en `/docs`. El token de desarrollo es `desarrollo-seguro`.

La composición levanta también Redis, utilizado por las opciones de caché e idempotencia.

```powershell
$headers = @{ Authorization = 'Bearer desarrollo-seguro' }
$e = Invoke-RestMethod http://localhost:8000/v1/estudiantes -Method Post -Headers $headers -ContentType application/json -Body '{"nombre":"Ana Perez","email":"ana@example.com"}'
$m = Invoke-RestMethod http://localhost:8000/v1/matriculas -Method Post -Headers $headers -ContentType application/json -Body "{\"estudiante_id\":\"$($e.id)\",\"curso_id\":\"ARQ-101\"}"
Invoke-RestMethod "http://localhost:8000/v1/matriculas/$($m.id)/revertir" -Method Post -Headers $headers
```

Para demostrar resiliencia, ejecute `docker compose stop cupos` y consulte o cree una matrícula: la API responderá `503` con JSON de problema. Un deadline agotado se traduce a `504`.

## Contratos y decisiones

- gRPC: [cupos.proto](cupos/cupos.proto)
- REST: [openapi.yaml](matriculas/openapi.yaml)
- Decisiones: [ADR](docs/adr)
- Informe PDF: [Informe-Forma-K.pdf](docs/Informe-Forma-K.pdf) (11 páginas; completar portada antes de entregar)
- Guion: [guion-video.md](docs/guion-video.md)

## Idempotencia y caché

`POST /v1/matriculas` acepta `Idempotency-Key`; una repetición durante 24 horas devuelve la respuesta guardada en Redis y no ocupa otro cupo. La consulta de curso usa cache-aside en Redis con TTL corto y se invalida al ocupar o liberar.

Las representaciones de matrículas incluyen `_links`: una matrícula activa expone la acción `revertir`; una revertida no. Esto evita ofrecer una transición inválida al cliente.

## Experimento sugerido

Hipótesis: protobuf usa menos bytes que JSON para un `Curso` equivalente. Serializar el mismo mensaje repetidamente con `SerializeToString()` y comparar `len()` con `json.dumps(...).encode()`; registrar versiones, número de repeticiones, media y desviación. La ejecución de validación obtuvo 39 bytes / 238 ns-op para protobuf y 94 bytes / 3.770 ns-op para JSON. Repítelo con `python docs/experimento_serializacion.py` si cambia el entorno.

## Pruebas

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests -v
```

## Uso de IA

Se usó asistencia de IA para estructurar código, contratos y documentación. El equipo debe revisar el código generado, ejecutar pruebas y explicar las decisiones y resultados del experimento.
