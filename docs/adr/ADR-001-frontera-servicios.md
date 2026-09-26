# ADR-001 · Frontera entre Cupos y Matrículas

**Estado:** aceptada

## Contexto

AprendeMás tiene sobrecupos porque Matrículas inscribe sin preguntar a Cupos. Los dos sistemas ya existen por separado, con dueños y ritmos de cambio distintos: Cupos cambia con la oferta académica y Matrículas con las reglas de inscripción. Cupos es la fuente de verdad de cuántos cupos quedan; Matrículas guarda datos personales de estudiantes. Hay que decidir dónde va la frontera y qué dato vive en cada lado.

## Alternativas consideradas

- **Monolito con una base compartida:** una transacción local resuelve "ocupar cupo + registrar matrícula" de forma atómica, pero obliga a fusionar dos sistemas que hoy tienen equipos y despliegues distintos.
- **Dos servicios con una base compartida:** separa procesos pero no la propiedad de los datos. Un cambio de esquema en un lado rompe al otro sin pasar por un contrato (el anti-patrón del monolito distribuido).
- **Dos servicios con base por servicio, frontera por bounded context:** cada servicio es dueño de sus datos y el otro solo accede por su contrato. Cuesta una llamada remota y renunciar a una transacción ACID entre ambos.

## Decisión

Dos servicios con base propia. Cupos es dueño de `Curso` y de sus contadores de cupos. Matrículas es dueño de `Estudiante` y `Matrícula`.

## Justificación

La frontera sigue la capacidad de negocio ("ofertar cursos" frente a "inscribir estudiantes"), que es el criterio de descomposición más estable. La regla que decide si hay cupo vive en un solo lugar: `OcuparCupo` verifica y descuenta de forma atómica dentro de Cupos, así que Matrículas nunca decide con una copia del contador. Separar las bases también limita la exposición de los datos personales, que solo existen en Matrículas.

Datos duplicados a propósito:

- `curso_id` dentro de cada matrícula. Es el único identificador compartido.
- Una copia de la disponibilidad en Redis, con TTL de 30 s, solo para `GET /v1/cursos/{id}`. Puede estar desactualizada hasta 30 s. Por eso no se usa para decidir matrículas: esa decisión siempre la toma Cupos.

## Costo aceptado

No hay transacción entre "ocupar cupo" (en Cupos) y "guardar matrícula" (en Matrículas). Si la escritura local falla después de ocupar, el cupo queda ocupado sin matrícula. Se acepta en vez de 2PC o Saga porque el volumen no lo justifica en esta etapa. Hay dos mitigaciones puntuales, sin compensación general:

- Si dos peticiones concurrentes intentan la misma matrícula activa, el índice único de SQLite rechaza la segunda y Matrículas devuelve el cupo con `LiberarCupo`.
- Al revertir, primero se marca la matrícula como `revertida` con un `UPDATE` condicional y recién después se libera el cupo. Si la liberación falla, la matrícula vuelve a `activa`. Así dos reversiones simultáneas no liberan el cupo dos veces.

## Consecuencias

Matrículas depende de la disponibilidad de Cupos para inscribir (ver ADR-004). Una versión de producción necesitaría un identificador de operación y una conciliación periódica entre matrículas activas y cupos ocupados. Si Cupos llegara a necesitar datos personales, esta frontera tendría que revisarse.
