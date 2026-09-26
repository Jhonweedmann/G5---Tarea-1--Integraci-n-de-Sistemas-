# ADR-002 · REST hacia afuera, gRPC hacia adentro

**Estado:** aceptada

## Contexto

La API de Matrículas la consumirán el personal de AprendeMás y un futuro portal web, es decir, clientes heterogéneos que incluyen navegadores. La llamada de Matrículas a Cupos es interna, ocurre en cada intento de matrícula y no la ve el exterior. Los dos lados tienen consumidores y necesidades distintas.

## Alternativas consideradas

- **REST/JSON en ambos lados:** un solo protocolo y cualquier cliente HTTP sirve. A cambio, el contrato interno se interpreta en vez de compilarse y los mensajes son más grandes.
- **gRPC en ambos lados:** contrato tipado y compilado en todas partes. Pero el navegador no puede hablar gRPC directamente: necesitaría gRPC-Web y un proxy, y el puerto interno quedaría expuesto a clientes externos.
- **REST hacia afuera y gRPC hacia adentro:** interoperabilidad universal en el borde y un contrato compilado entre servicios, con dos contratos que mantener.

## Decisión

API pública REST/JSON bajo `/v1`. Comunicación Matrículas → Cupos con gRPC y Protocol Buffers. `ConsultarCurso`, `OcuparCupo` y `LiberarCupo` son unarias; `ListarCursos` es *server streaming*.

## Justificación

- **Tamaño:** según `docs/experimento_serializacion.py`, un `Curso` ocupa 39 bytes en protobuf y 94 en JSON (0,41×). En listas de 10 a 1000 cursos la proporción se mantiene en ~0,40×. El matiz es que con gzip la diferencia se reduce a 0,73–0,85×. La ventaja de tamaño es real, pero no es el argumento principal.
- **Contrato compilado:** el argumento principal es que Matrículas usa clases generadas desde `cupos.proto`. Un campo mal escrito o con el tipo equivocado produce un error inmediato al construir el mensaje, que las pruebas detectan. Con JSON, en cambio, el error pasaría en silencio hasta que el servidor interpretara mal el dato.
- **Interoperabilidad:** un cliente Node.js consume el mismo `.proto` sin modificar el servidor.
- **Modos de invocación:** `ListarCursos` es streaming porque el catálogo puede crecer y el cliente procesa cada curso a medida que llega. Las otras tres operaciones resuelven una sola pregunta o una sola escritura atómica, así que son unarias.

## Costo aceptado

Hay dos contratos (`openapi.yaml` y `cupos.proto`), dos formatos y dos juegos de herramientas de depuración. gRPC no se inspecciona con curl ni con el navegador.

## Consecuencias

- `docker-compose.yml` no publica el puerto 50051: Cupos solo es alcanzable dentro de la red de Compose. Por eso el cliente Node (O5) corre como un contenedor más, con el perfil `demo`.
- Los stubs se generan en el build de cada imagen a partir del único `cupos/cupos.proto` y no se versionan, para que ningún consumidor use una copia desactualizada del contrato.
- Si un cliente externo necesitara streaming, se evaluaría gRPC-Web con proxy, sin exponer el puerto interno.
