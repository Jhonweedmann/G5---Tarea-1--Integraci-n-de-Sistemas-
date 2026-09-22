# ADR-004 · Fallas y tiempos de espera de Cupos

**Estado:** aceptada

## Contexto

Matrículas depende de Cupos para decidir una matrícula. Una caída o lentitud no puede generar una traza HTTP ni permitir matricular sin validar disponibilidad.

## Alternativas consideradas

- **Esperar sin deadline:** maximiza intentos exitosos, pero agota hilos bajo una dependencia lenta.
- **Aceptar con caché obsoleta:** conserva disponibilidad, pero puede sobrepasar la capacidad de la sala.
- **Fail fast con deadline y error explícito:** protege al llamador, sacrificando disponibilidad temporal.

## Decisión y justificación

El canal gRPC reutilizable usa deadline de 2 s. `UNAVAILABLE` se traduce a HTTP 503 y `DEADLINE_EXCEEDED` a 504 con `application/problem+json`; ambos permiten reintento. Redis acelera consultas, pero `OcuparCupo` sigue siendo la decisión atómica del dueño de cupos.

## Costo aceptado y consecuencias

Una falla recuperable puede rechazar temporalmente una matrícula y requiere reintento con `Idempotency-Key`. Se debe medir apagando Cupos durante la demo; si la latencia normal supera 2 s, el timeout se revisa con datos.
