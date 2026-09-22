# ADR-003 · Evolución compatible de contratos

**Estado:** aceptada

## Contexto

Los contratos tienen consumidores independientes y deben evolucionar sin que un despliegue de servidor rompa a los clientes anteriores.

## Alternativas consideradas

- **Sin versión explícita:** menos rutas, pero un cambio incompatible es ambiguo y riesgoso.
- **Cambiar `/v1` en sitio y reutilizar tags protobuf:** rápido, pero rompe clientes aún en la representación previa.
- **Versionado REST por ruta y evolución aditiva protobuf:** permite migración gradual; requiere disciplina documental.

## Decisión y justificación

REST usa `/v1`; un cambio incompatible crea `/v2` y se anuncia con retiro. En protobuf se agregan campos con nuevos números, nunca se renumeran ni reutilizan tags eliminados; los consumidores previos ignoran campos desconocidos. `descripcion = 5` es compatible. Cambiar significado, tipo incompatible o número exige nueva versión del mensaje/RPC.

## Costo aceptado y consecuencias

Durante migración se mantienen representaciones y se documentan consumidores y fecha de deprecación. El CI debe regenerar stubs y ejecutar pruebas de contrato antes de publicar un proto nuevo.
