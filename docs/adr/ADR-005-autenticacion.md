# ADR-005 · Autenticación y autorización en la API REST

**Estado:** aceptada

## Contexto

La API expone datos personales de estudiantes y operaciones que ocupan cupos. La consumen el personal de AprendeMás y un futuro portal web. Hay que saber quién llama (autenticación) y distinguir al menos entre quien solo consulta y quien matricula (autorización), declarándolo en el contrato OpenAPI.

## Alternativas consideradas

- **Basic Auth:** estándar y simple, pero viaja un usuario y contraseña en cada petición y exige un almacén de contraseñas que el sistema no tiene.
- **API Key en un header propio (por ejemplo `X-API-Key`):** igual de simple, pero no es un esquema HTTP estándar y no tiene una forma definida de indicar en la respuesta por qué se rechazó la credencial.
- **JWT firmado:** lleva identidad, roles y expiración, y se verifica sin consultar a nadie. Exige gestionar claves y emisión de tokens, y revocarlo antes de que expire es difícil. Excede lo que el sistema necesita hoy.
- **Bearer con tokens opacos por rol:** esquema estándar (RFC 6750) que OpenAPI declara de forma nativa. El servidor compara el token contra los configurados.

## Decisión

`Authorization: Bearer <token>` con dos tokens opacos configurados por variables de entorno:

| Token | Variable | Permite |
|---|---|---|
| Escritura | `API_TOKEN` | Todas las operaciones |
| Lectura | `API_TOKEN_LECTURA` | Solo `GET` |

Semántica de los códigos:

- **401** con `WWW-Authenticate: Bearer`: falta el token o es desconocido, es decir, no se sabe quién llama. Si el token es desconocido, la cabecera agrega `error="invalid_token"`.
- **403**: el token es válido pero no alcanza para la operación, por ejemplo el token de lectura intentando un `POST`.

Los tokens se comparan en tiempo constante (`hmac.compare_digest`). `/health`, `/docs` y el contrato quedan públicos.

## Justificación

Siendo honestos, un token opaco fijo funciona como una API Key: identifica a un tipo de cliente, no a una persona, y no expira solo. Se prefirió enviarlo como Bearer y no en un header propio porque es el esquema estándar que Swagger UI, curl y Postman entienden sin configuración. Además, RFC 6750 define cómo responder el 401 (`WWW-Authenticate` con `error="invalid_token"`), y el cliente no cambia si mañana el token pasa a ser un JWT. Con dos roles, el 403 tiene un caso real en vez de ser un código declarado que nunca ocurre.

## Costo aceptado

- Los tokens son secretos compartidos, no personales: no permiten auditar qué persona hizo cada matrícula.
- Si un token se filtra, hay que rotarlo para todos sus usuarios.
- Sin TLS delante de la API, el token viaja en claro. En producción es obligatorio terminar TLS antes de Matrículas.

## Consecuencias

Una versión de producción reemplazaría los tokens fijos por JWT de vida corta emitidos por un proveedor de identidad, con el rol como claim. El contrato OpenAPI no cambiaría, porque sigue siendo `bearerAuth`.
