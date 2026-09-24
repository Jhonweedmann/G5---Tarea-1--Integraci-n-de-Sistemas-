
**Forma K — Sistema de Gestión de Cursos y Matrículas**
**Informe de Unidad 1 · Integración de Sistemas**
Universidad de Concepción — Facultad de Ingeniería
Docente: Gonzalo Pérez Correa

**Grupo:** [completar]
**Integrantes:**
- [Nombre completo integrante 1]
- [Nombre completo integrante 2]
- [Nombre completo integrante 3]
- [Nombre completo integrante 4 — si aplica]

**Fecha:** [completar]


# Informe — Forma K: Cursos y Matrículas

## 1. Problema y solución

### 1.1 Contexto

La Centro de Formación Técnica AprendeMás opera hoy con dos sistemas que nacieron por separado y nunca conversaron entre sí:

- **Cupos**: administra los cursos y los cupos disponibles de cada uno. Es donde vive la verdad sobre qué cursos se dictan y cuántos cupos quedan en cada uno.
- **Matrículas**: registra a los estudiantes y sus matrículas. Necesita saber, para cada curso, si hay cupos disponibles antes de matricular a un estudiante, y consulta esa información con muchísima frecuencia.

Hoy los dos sistemas no están integrados: se matricula sin verificar cupos y algunos cursos superan la capacidad de la sala. La organización encargó una solución de integración que resuelva este problema.

### 1.2 Solución

La matrícula requiere datos académicos y una disponibilidad de cupos que deben mantenerse como responsabilidades separadas. La solución tiene dos servicios: **Matrículas** gestiona estudiantes y matrículas mediante REST; **Cupos** gestiona los cursos mediante gRPC. Sus bases SQLite no se comparten. Redis entrega caché de disponibilidad e idempotencia. Cuando la API REST recibe una solicitud de matrícula, consulta al servicio gRPC de Cupos para decidir si el curso está disponible antes de confirmar la inscripción — así se cierra la brecha que hoy permite matricular sin cupo.

Antes de escribir código se tomaron cuatro decisiones de fondo, documentadas como ADR en `docs/adr/`: la frontera entre servicios (ADR-001), el protocolo hacia cada lado (ADR-002), la estrategia de evolución del contrato (ADR-003) y el manejo de fallas (ADR-004), más una quinta sobre autenticación (ADR-005). Este informe explica esas decisiones en conjunto, incluyendo qué otras opciones eran viables y por qué se descartaron.

## 2. Estilo arquitectónico: microservicios

**Decisión:** dos servicios independientes, cada uno con su propio proceso, base de datos y ciclo de despliegue, divididos por *bounded context*: Cupos posee `Curso` y sus contadores; Matrículas posee `Estudiante` y `Matrícula`.

### 2.1 Alternativas consideradas

| Opción | Qué ofrece | Por qué no se eligió |
|---|---|---|
| **Monolito** (todo en un proceso, una base de datos) | Transacción local simple, sin llamadas de red, cero costo de coordinación | Acopla a los dos equipos y ciclos de vida que hoy son distintos: Cupos cambia con la oferta académica, Matrículas con las reglas de inscripción. Un solo despliegue frenaría a ambos. Es una opción legítima si un solo equipo mantuviera ambos dominios, pero no resuelve el problema real, que es la falta de comunicación entre dos sistemas que **ya existen por separado**. |
| **Monolito en capas** (presentación / lógica / datos, un solo despliegue) | Organización interna clara, sigue siendo una sola unidad desplegable | Mismo problema que el monolito simple desde el punto de vista de integración: resuelve el eje "cómo se organiza por dentro", no el eje "cómo se comunican dos sistemas", que es el problema que el encargo plantea. |
| **Arquitectura hexagonal dentro de un único servicio** | Aísla el núcleo de negocio de la tecnología de persistencia o transporte | Es un patrón de organización interna (eje 1), no de descomposición entre sistemas (eje 2). Podría aplicarse dentro de cada microservicio, pero no reemplaza la necesidad de separar Cupos de Matrículas. |
| **Dos servicios con base de datos compartida** | Evita la llamada remota para leer datos del otro dominio; consultas SQL directas y JOIN entre tablas | Es el anti-patrón "monolito distribuido": se pagan los costos de la distribución (dos despliegues, dos procesos) sin ganar autonomía real, porque un cambio de esquema en un servicio puede romper al otro sin que medie ningún contrato. |
| **Microservicios con base de datos por servicio** (elegida) | Autonomía real: cada servicio evoluciona su esquema sin coordinar con el otro; el único acceso a los datos ajenos es a través de la API/contrato del dueño | Cuesta una llamada remota para cruzar información y renuncia a una transacción ACID entre ambos dominios (ver §2.2) |

### 2.2 Costo aceptado

La matrícula cruza la red: puede ocurrir que se ocupe un cupo en Cupos y la escritura local en Matrículas falle después. Se acepta ese riesgo en vez de introducir una transacción distribuida (2PC) o un mecanismo de compensación tipo Saga, porque el volumen y la criticidad del dominio no lo justifican en esta etapa; una versión de producción debería agregar un identificador de operación y un proceso de conciliación periódica.

## 3. Estilo de integración: invocación remota

El catálogo de Enterprise Integration Patterns define cuatro estilos para que dos sistemas colaboren. El proyecto usa **invocación remota**; los otros tres se descartaron por razones concretas del dominio:

| Estilo de integración | Por qué no aplica aquí |
|---|---|
| **Transferencia de archivos** (por ejemplo, un batch nocturno de cupos disponibles) | La disponibilidad de cupos cambia con cada matrícula; un archivo periódico dejaría a Matrículas trabajando con datos obsoletos y permitiría sobrecupos, exactamente el problema que el encargo pide resolver. |
| **Base de datos compartida** | Ya descartada en §2.1: rompe la propiedad de los datos y crea acoplamiento de esquema entre dos equipos que deben poder evolucionar por separado. |
| **Mensajería** (cola o tópico con un broker) | Es la respuesta natural cuando la relación es "avísame cuando algo cambie" y se tolera consistencia eventual. Aquí la pregunta es "¿hay cupo *ahora mismo*, antes de confirmar esta matrícula?": es una decisión síncrona que bloquea o permite una operación de negocio, no un evento que se pueda propagar con demora. Mensajería es contenido de la Unidad 2 del curso (asincronía) y queda fuera del alcance de este encargo, que trabaja explícitamente sobre comunicación síncrona. |
| **Invocación remota** (elegida) | Matrículas necesita una respuesta inmediata de Cupos para decidir si matricula o rechaza. Es el estilo correcto cuando la operación es una pregunta-respuesta que debe resolverse en el momento. |

Dentro de invocación remota, también se descartó explícitamente el patrón **SOA con bus (ESB)**: exigiría una gobernanza centralizada, contratos WSDL/SOAP y un equipo que administre el bus, todo pensado para organizaciones con decenas de sistemas heredados e inmodificables. AprendeMás tiene dos sistemas propios y un equipo que los controla por completo — exactamente el contexto donde microservicios rinde mejor que SOA, no al revés.

## 4. REST hacia afuera, gRPC hacia adentro

**Decisión (ADR-002):** la API pública de Matrículas es REST/JSON bajo `/v1`; la comunicación Matrículas → Cupos es gRPC/Protocol Buffers.

### 4.1 Alternativas consideradas

| Opción | A favor | En contra |
|---|---|---|
| **REST/JSON en ambos lados** | Un solo protocolo que aprender y depurar; cualquier cliente HTTP sirve, incluso para la llamada interna | Sin contrato compilado (un cliente puede interpretar mal el JSON en tiempo de ejecución, no de compilación); sin streaming nativo; y en el experimento del informe, el mensaje `Curso` en JSON pesó 94 bytes contra 39 en protobuf — más del doble, sobre una llamada que Matrículas hace en cada intento de matrícula |
| **gRPC en ambos lados** | Contrato tipado y generado también hacia afuera; más eficiente en el borde también | El navegador no puede hablar gRPC nativamente (no expone el framing binario de HTTP/2 ni los trailers donde viaja el código de estado); expondría un servicio interno de alto volumen directamente a clientes externos, mezclando dos superficies de confianza distintas |
| **REST hacia afuera, gRPC hacia adentro** (elegida) | Cada protocolo se usa donde su costo se paga con una ventaja real: interoperabilidad en el borde, contrato tipado y eficiencia en el tráfico interno de alto volumen | Duplica la superficie de mantenimiento: dos contratos (`openapi.yaml` y `cupos.proto`), dos formatos, dos juegos de herramientas de depuración |

Dentro de gRPC, `ListarCursos` usa **server streaming** en vez de una llamada unaria, porque el catálogo de cursos puede crecer y el criterio del curso es "si el resultado es grande o se produce con el tiempo, streaming; si es una respuesta corta y completa, unaria". `ConsultarCurso`, `OcuparCupo` y `LiberarCupo` sí son unarios, porque cada uno resuelve una sola pregunta o una sola escritura atómica. Se descartó **client streaming** y **bidireccional** por no existir ningún caso de uso en este dominio que envíe muchos mensajes hacia Cupos o que necesite un canal abierto en ambos sentidos (eso correspondería a un chat o una negociación por rondas, no a matricular estudiantes).

Si en el futuro un cliente externo necesitara streaming, la vía sería **gRPC-Web con un proxy**, no abrir el puerto interno del servicio de Cupos directamente — así queda anotado en el ADR-002 como decisión pendiente y no como omisión.

## 5. Patrones implementados y alternativas descartadas

| Necesidad | Patrón elegido | Cómo se implementó | Alternativas descartadas y por qué |
|---|---|---|---|
| Evitar recalcular la disponibilidad en cada consulta | **Cache-aside con Redis** | `GET /v1/cursos/{id}` busca primero en Redis; si no está, consulta a Cupos por gRPC y guarda el resultado con TTL de 30 s; toda escritura (`ocupar`/`liberar`) invalida la clave | *Sin caché*: cada consulta golpea a Cupos por gRPC, lo cual es correcto pero más lento bajo carga. *Write-through*: actualizar la caché en cada escritura de Cupos en vez de invalidar desde Matrículas — se descartó porque acoplaría a Cupos con la existencia de una caché en un consumidor suyo, violando la frontera de servicio. |
| Evitar que un reintento de red duplique una matrícula | **Idempotent Receiver** vía `Idempotency-Key` | El cliente envía un identificador único por intención de matrícula; Redis recuerda el resultado 24 h y lo devuelve tal cual ante una clave repetida, sin volver a ocupar un cupo | *Sin idempotencia* (dejar que el cliente no reintente): no resuelve el problema real, porque el cliente puede perder la respuesta sin saber si la operación se ejecutó. *Deduplicar por contenido* (mismo `estudiante_id` + `curso_id` en una ventana de tiempo): más frágil, porque un estudiante podría legítimamente querer dos matrículas similares más adelante, y el criterio "misma intención" ya lo captura mejor una clave explícita que genera el cliente. |
| Comunicar qué acciones son válidas desde el estado actual de una matrícula | **HATEOAS** | La respuesta de una matrícula incluye `_links`; el enlace `revertir` solo aparece si el estado es `activa` | *Documentar las transiciones solo en el OpenAPI* (sin enlaces en la respuesta): es más liviano y es lo que se usa en el resto de la API (estudiantes, cursos), pero para matrículas se prefirió HATEOAS porque el estado de una matrícula cambia (activa → revertida) y el enlace evita que el cliente necesite conocer de memoria qué transición es válida. La validación real igual ocurre en el servidor, no se confía solo en que el cliente respete lo que ve. |
| Formato uniforme de errores | **Problem Details (RFC 9457)** | Todo error HTTP responde `application/problem+json` con `type/title/status/detail` | *Formato propio* (`{"error": "mensaje"}`): más simple de escribir, pero cada API termina inventando su propia forma, y un cliente que consume varias APIs debe aprender un formato distinto por cada una. RFC 9457 es un estándar existente y evita esa fragmentación. |
| Evolucionar el contrato sin romper consumidores | **Versionado por ruta** (`/v1`) en REST; **evolución aditiva de números de campo** en protobuf | Un cambio incompatible crearía `/v2`; en protobuf se agregan campos nuevos con números nuevos, nunca se reutilizan los eliminados | *Versionado por cabecera* (`Accept: ...;version=1`): más "puro" porque la URL identifica solo el recurso, pero invisible en el navegador y más difícil de depurar en la defensa oral. *Sin versión, solo cambios aditivos*: exige una disciplina muy alta y un mecanismo de deprecación que el equipo no tiene la madurez operacional para sostener en un proyecto de este tamaño. |
| Responder ante una dependencia caída o lenta | **Fail-fast con deadline** | El canal gRPC usa un deadline de 2 s; `UNAVAILABLE` → 503, `DEADLINE_EXCEEDED` → 504, ambos reintentables con `Idempotency-Key` | *Esperar sin deadline*: maximiza el número de matrículas que terminan bien, pero agota hilos/conexiones si Cupos está lento, arrastrando a Matrículas con él. *Aceptar con la última caché conocida*: mantiene el servicio disponible, pero puede autorizar una matrícula sobre un cupo que ya no existe — es precisamente el sobrecupo que el encargo pide evitar. Se prefirió sacrificar disponibilidad temporal antes que la corrección del dato de cupos. |
| Identificar al llamador de la API pública | **Bearer Token** | Header `Authorization: Bearer <token>`, declarado en OpenAPI (`securitySchemes: bearerAuth`); 401 si falta, 403 si no corresponde | *Basic Auth*: envía credenciales codificadas (no cifradas) en cada petición y se degrada mal sin TLS mutuo. *API Key en query string*: queda expuesta en logs de proxy e historial del navegador. Bearer se eligió porque no repite credenciales sensibles por petición y migra sin fricción a JWT u OAuth2 si el sistema crece. |

## 6. Arquitectura

```text
Cliente HTTP ──REST /v1──> Matrículas ──gRPC/protobuf──> Cupos
                              │                            │
                         SQLite matrículas              SQLite cupos
                              │
                            Redis
```

Los contratos se encuentran en `matriculas/openapi.yaml` y `cupos/cupos.proto`. Las decisiones de frontera, protocolo, versionado, resiliencia y autenticación están justificadas en detalle en `docs/adr/` (ADR-001 a ADR-005); las secciones 2 a 5 de este informe resumen ese razonamiento y lo contrastan explícitamente con lo que se descartó.

## 7. Flujo y fallas

Al crear una matrícula se valida el estudiante, se consulta y ocupa un cupo por gRPC, y se persiste la matrícula activa. Revertir libera el cupo y cambia el estado. Si Cupos no está disponible, Matrículas responde 503; si vence el deadline gRPC, responde 504. Ambos casos usan `application/problem+json` sin exponer trazas internas.

## 8. Seguridad y contexto

La API exige Bearer token para sus recursos. En un sistema real, el token fijo de desarrollo debe reemplazarse por validación JWT, secretos administrados y autorización por roles. Los datos de estudiantes son personales: se debe limitar acceso a las bases, registrar auditoría y definir retención de datos. Este factor de contexto (privacidad de datos personales) es también parte de por qué se descartó la base de datos compartida en §2.1: mezclar los datos de Cupos (públicos, oferta académica) con los de Matrículas (personales) en un mismo almacén habría ampliado innecesariamente la superficie de exposición de datos sensibles.

## 9. Opcionales

Redis guarda respuestas de `Idempotency-Key` durante 24 horas, evitando ocupaciones duplicadas. La disponibilidad usa cache-aside e invalida la clave después de ocupar o liberar un cupo. Ambos patrones están descritos con sus alternativas en la tabla de la sección 5.

## 10. Experimento

Hipótesis: un `Curso` protobuf serializado ocupa menos bytes que su equivalente JSON y puede serializarse más rápido. El script realiza diez series de 10.000 operaciones, informando tamaño, media y desviación estándar. En la ejecución de validación (Python 3.14, Windows) obtuvo 39 bytes y 238 ns/op ± 72 para protobuf, frente a 94 bytes y 3.770 ns/op ± 273 para JSON. Los datos respaldan la hipótesis para este mensaje y son parte de la evidencia concreta detrás de la decisión de la sección 4 (gRPC hacia adentro); deben repetirse si cambia el hardware, runtime o esquema.

## 11. Resumen de decisiones descartadas

| Nivel de decisión | Se eligió | Se descartó |
|---|---|---|
| Organización interna | Microservicios (2 servicios, BD propia) | Monolito, monolito en capas, hexagonal como reemplazo de la separación, microservicios con BD compartida |
| Estilo de integración | Invocación remota | Transferencia de archivos, base de datos compartida, mensajería |
| Gobernanza de la integración | Descentralizada, contratos livianos | SOA con ESB, bus centralizado, WSDL/SOAP |
| Protocolo externo | REST/JSON | gRPC expuesto directamente, REST sin versión |
| Protocolo interno | gRPC/Protobuf, unario + server streaming | REST/JSON interno, client streaming, bidireccional |
| Caché | Cache-aside con invalidación | Sin caché, write-through desde Cupos |
| Reintentos duplicados | Idempotent Receiver (`Idempotency-Key`) | Sin idempotencia, deduplicación por contenido |
| Ante falla de Cupos | Fail-fast con deadline (503/504) | Esperar sin deadline, servir caché obsoleta como autorización |
| Autenticación | Bearer Token | Basic Auth, API Key en query |

## 12. Reflexión

La separación protege la propiedad de los datos y permite escalar Cupos de forma independiente. El costo es que una operación de negocio atraviesa la red: por ello los contratos, deadlines, códigos de error y pruebas de caída son parte del diseño, no detalles posteriores. Cada decisión de esta tabla tiene un costo aceptado explícito (detallado en los ADR correspondientes); lo que se buscó no fue la opción "mejor" en abstracto, sino la que mejor responde a las restricciones reales de AprendeMás: dos equipos con datos de naturaleza distinta, una consulta de disponibilidad de alto volumen, y una necesidad de respuesta inmediata que descarta tanto la mensajería como la base de datos compartida.
