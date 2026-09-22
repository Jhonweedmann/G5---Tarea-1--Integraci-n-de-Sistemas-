# ADR-001 · Frontera entre Cupos y Matrículas

**Estado:** aceptada

## Contexto

AprendeMás necesita impedir sobrecupos, pero Cupos y Matrículas tienen propietarios y ritmos de cambio distintos. Cupos es la fuente de verdad de la oferta; Matrículas conserva datos personales e historial. Ningún servicio puede escribir en el almacén del otro.

## Alternativas consideradas

- **Monolito con una base compartida:** simplifica una transacción local, pero acopla equipos, despliegues y esquemas.
- **Dos servicios con una base compartida:** separa procesos, pero no propiedad de datos; una modificación al esquema puede romper ambos.
- **Dos servicios y base por servicio:** mantiene la frontera, a costa de una llamada remota y consistencia no distribuida.

## Decisión y justificación

Se elige la tercera opción. Cupos posee `Curso` y los contadores; Matrículas posee `Estudiante` y `Matrícula`. Solo se duplica el identificador de curso dentro de una matrícula, no la disponibilidad. La separación permite escalar o reemplazar Cupos sin exponer su base.

## Costo aceptado y consecuencias

La matrícula cruza la red y puede fallar después de ocupar un cupo antes de persistir localmente. Se acepta ese riesgo para evitar transacciones distribuidas; producción añadiría reserva con identificador de operación y conciliación. Si Cupos requiere datos personales, esta frontera debe revisarse.
