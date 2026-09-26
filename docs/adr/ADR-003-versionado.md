# ADR-003 · Contratos, versionado y evolución

**Estado:** aceptada

## Contexto

Los dos contratos tienen consumidores que el equipo no controla del todo: el portal y el personal consumen la API REST, y Matrículas y el cliente Node consumen `cupos.proto`. Si mañana hay que agregar un campo, hay que saber qué cambios se pueden desplegar sin coordinar, cuáles exigen una versión nueva y cómo se entera cada consumidor.

## Alternativas consideradas

- **Sin versión, solo cambios aditivos:** no hay rutas duplicadas, pero exige una disciplina alta y un mecanismo de deprecación que el equipo aún no opera.
- **Versión en cabecera (`Accept: ...;version=1`):** la URL identifica solo el recurso, pero la versión no se ve en el navegador y es más difícil de depurar.
- **Versión en la ruta (`/v1`) y evolución aditiva en protobuf:** visible y fácil de enrutar. Obliga a mantener `/v1` mientras exista una `/v2`.

## Decisión

REST versionado en la ruta (`/v1`), con el contrato escrito a mano (contract-first) en `matriculas/openapi.yaml`. Ese archivo es el que la API publica en `/openapi.json`, `/openapi.yaml` y `/docs`. En gRPC, `package cupos.v1` con evolución aditiva de números de campo.

## Justificación

| Cambio | REST (`/v1`) | protobuf (`cupos.v1`) |
|---|---|---|
| Agregar un campo a una respuesta (por ejemplo `cupos_totales` en `Curso`) | Compatible: el cliente lo ignora. Se actualiza el esquema del YAML y las pruebas de contrato | Compatible: nuevo número (`= 5`). Los clientes viejos lo ignoran y los nuevos reciben el valor por defecto si falta |
| Agregar un parámetro opcional o un endpoint | Compatible | Compatible (nuevo RPC) |
| Renombrar o eliminar un campo | Incompatible: exige `/v2` | Renombrar no cambia el binario, pero rompe el código de quien usa el nombre al regenerar los stubs. Eliminar exige marcar el número como `reserved` para que nunca se reutilice |
| Cambiar el tipo o el significado de un campo | Incompatible: `/v2` | Incompatible: nuevo campo o `cupos.v2` |
| Volver obligatorio un parámetro opcional | Incompatible: `/v2` | No aplica (proto3 no tiene campos obligatorios) |

La paginación (`limit` y `offset`, con 20 por defecto y 100 como máximo) se incluyó desde `/v1`, porque agregarla después cambiaría la forma de la respuesta de lista, lo que es un cambio incompatible.

## Costo aceptado

Mientras conviven `/v1` y `/v2` hay que mantener dos representaciones sobre la misma lógica. El contrato escrito a mano exige más trabajo al principio que uno generado desde el código.

## Consecuencias

Cómo se enteran los consumidores:

1. El contrato vive en el repositorio y cualquier cambio se revisa en el pull request.
2. La API publica siempre el contrato vigente en `/openapi.yaml`.
3. Las pruebas de contrato (`tests/test_api.py`) validan cada respuesta real contra el YAML, con `additionalProperties: false`. Un campo nuevo que no se declaró rompe las pruebas antes de llegar a un consumidor.
4. Al deprecar `/v1`, sus respuestas agregarían la cabecera `Sunset` (RFC 8594) con la fecha de retiro. Además se registraría quién sigue usando `/v1` antes de apagarla.

En gRPC, los stubs se regeneran desde `cupos.proto` en cada build, así que un cambio del contrato llega a todos los consumidores de este repositorio en el siguiente despliegue.
