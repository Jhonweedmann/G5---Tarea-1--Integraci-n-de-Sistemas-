# ADR-002 · REST público y gRPC interno

**Estado:** aceptada

## Contexto

La API será consumida por personal y un eventual portal web, mientras Matrículas consulta Cupos con frecuencia en una red interna. Se necesita un contrato entendible para clientes heterogéneos y uno tipado para el vínculo interno.

## Alternativas consideradas

- **REST/JSON para todo:** fácil de inspeccionar, pero sin stubs generados ni streaming nativo.
- **gRPC para todo:** eficiente y tipado, pero navegador y herramientas externas requieren gateway o cliente adicional.
- **REST externo y gRPC interno:** interoperabilidad en el borde y contrato binario generado entre servicios.

## Decisión y justificación

Se elige REST/JSON bajo `/v1` hacia afuera y gRPC/protobuf internamente. El experimento obtuvo 39 bytes para `Curso` protobuf frente a 94 bytes JSON. `ListarCursos` es *server streaming*: Cupos produce un curso por vez, sin construir una lista completa al crecer el catálogo.

## Costo aceptado y consecuencias

Hay dos tecnologías, contratos y herramientas de depuración. OpenAPI y `.proto` se versionan juntos. Si un cliente externo requiere streaming se evaluará gRPC-Web, no se expondrá directamente el puerto interno.
