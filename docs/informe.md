# Informe — Forma K: Cursos y Matrículas

## Problema y solución

La matrícula requiere datos académicos y una disponibilidad de cupos que deben mantenerse como responsabilidades separadas. La solución tiene dos servicios: Matrículas gestiona estudiantes y matrículas mediante REST; Cupos gestiona los cursos mediante gRPC. Sus bases SQLite no se comparten. Redis entrega caché de disponibilidad e idempotencia.

## Arquitectura

```text
Cliente HTTP ──REST /v1──> Matrículas ──gRPC/protobuf──> Cupos
                              │                            │
                         SQLite matrículas              SQLite cupos
                              │
                            Redis
```

Los contratos se encuentran en `matriculas/openapi.yaml` y `cupos/cupos.proto`. Las decisiones de frontera, protocolo, versionado y resiliencia están justificadas en `docs/adr`.

## Flujo y fallas

Al crear una matrícula se valida el estudiante, se consulta y ocupa un cupo por gRPC, y se persiste la matrícula activa. Revertir libera el cupo y cambia el estado. Si Cupos no está disponible, Matrículas responde 503; si vence el deadline gRPC, responde 504. Ambos casos usan `application/problem+json` sin exponer trazas.

## Seguridad y contexto

La API exige Bearer token para sus recursos. En un sistema real, el token fijo de desarrollo debe reemplazarse por validación JWT, secretos administrados y autorización por roles. Los datos de estudiantes son personales: se debe limitar acceso a las bases, registrar auditoría y definir retención de datos.

## Opcionales

Redis guarda respuestas de `Idempotency-Key` durante 24 horas, evitando ocupaciones duplicadas. La disponibilidad usa cache-aside e invalida la clave después de ocupar o liberar un cupo.

## Experimento

Hipótesis: un `Curso` protobuf serializado ocupa menos bytes que su equivalente JSON y puede serializarse más rápido. El script realiza diez series de 10.000 operaciones, informando tamaño, media y desviación estándar. En la ejecución de validación (Python 3.14, Windows) obtuvo 39 bytes y 238 ns/op ± 72 para protobuf, frente a 94 bytes y 3.770 ns/op ± 273 para JSON. Los datos respaldan la hipótesis para este mensaje; deben repetirse si cambia el hardware, runtime o esquema.

## Reflexión

La separación protege la propiedad de los datos y permite escalar Cupos de forma independiente. El costo es que una operación de negocio atraviesa la red: por ello los contratos, deadlines, códigos de error y pruebas de caída son parte del diseño, no detalles posteriores.
