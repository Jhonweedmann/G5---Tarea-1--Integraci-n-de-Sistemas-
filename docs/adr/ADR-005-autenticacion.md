# ADR-005 · Autenticación Bearer en la API REST

**Estado:** aceptada

## Contexto

La API REST de Matrículas es consumida por personal de AprendeMás y un eventual portal web. Se necesita un mecanismo que identifique al llamador, sea sencillo de implementar en cualquier cliente HTTP, y que se defienda fácilmente en el contrato OpenAPI.

## Alternativas consideradas

- **Basic Auth**: fácil de implementar, pero envía credenciales codificadas en base64 en cada solicitud; inadecuado cuando el tráfico no termina en TLS mutuo y expone el token en logs y proxies intermedios.
- **API Key en query string o header personalizado**: simple, pero la clave queda expuesta en URLs (logs de proxy, historial de navegador) y no se integra de forma natural con el ecosistema estándar de OAuth2/OpenAPI.
- **Bearer Token**: el cliente envía un token previamente acordado en el header `Authorization: Bearer <token>`; no hay credenciales en cada petición, el token puede ser efímero, y OpenAPI lo soporta de forma nativa con `securitySchemes`.

## Decisión y justificación

Se elige **Bearer Token** con API Key estática para desarrollo (`desarrollo-seguro`) y tokens rotables en producción. Se declara en el contrato OpenAPI como `securitySchemes: bearerAuth` de tipo `http` con esquema `bearer`, y se aplica a todas las rutas mediante `security: [{bearerAuth: []}]`, con excepción de `/health`, `/docs` y `/openapi.json`. El middleware en `main.py` valida el header `Authorization` antes de enrutar cualquier petición a los recursos de estudiantes o matrículas.

Justificaciones concretas:
1. **Estándar HTTP**: es el esquema definido por RFC 6750 y soportado nativamente por OpenAPI 3.0, lo que permite que herramientas (Swagger UI, Postman, curl) lo consuman sin configuración adicional.
2. **Sin credenciales por petición**: a diferencia de Basic Auth, el token no expone información sensible en cada llamada; si se filtra, puede revocarse sin cambiar la contraseña del usuario.
3. **Evolución futura**: un token Bearer puede migrarse fácilmente a un JWT con claims o a OAuth2 sin cambiar la estructura del header, manteniendo compatibilidad con el contrato vigente.
4. **Alineación con T3**: el mecanismo está declarado explícitamente en `openapi.yaml`, cumpliendo el requisito de contrato explícito.

## Costo aceptado y consecuencias

Para desarrollo se usa un token fijo; en producción debe reemplazarse por tokens firmados y de vida corta. El middleware añade una rama de evaluación por petición, pero el costo es despreciable. Si un cliente omite o invalida el token, recibe 401 o 403 con `application/problem+json`, consistente con el resto de la API.
