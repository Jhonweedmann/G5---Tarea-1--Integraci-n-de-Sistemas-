# Forma A — Sistema de Gestión de Cursos y Matrículas

## Informe de Integración de Sistemas

**Dominio:** Forma A  
**Grupo:** Forma A  
**Integrantes:** [Integrante 1], [Integrante 2], [Integrante 3]  
**Asignatura:** Integración de Sistemas  
**Fecha:** Septiembre 2026  
**Universidad de Concepción — Facultad de Ingeniería**

---

# 1. Análisis del problema

## 1.1 Qué se pide

AprendeMás opera dos sistemas que evolucionaron de forma independiente. **Cupos** conoce la oferta académica de cursos y la capacidad restante de cada asignatura. **Matrículas** almacena los datos de los estudiantes y su historial de inscripciones. Sin una integración explícita, existe el riesgo real de que una matrícula se confirme cuando no quedan cupos disponibles en una sala, generando sobrecupos y inconsistencia operativa.

El sistema solicitado debe resolver lo siguiente:

- **Gestión de estudiantes:** permitir crear, consultar y listar estudiantes en el sistema de Matrículas.
- **Gestión de matrículas:** matricular a un estudiante verificando la disponibilidad contra el sistema de Cupos; revertir la operación; consultar y listar matrículas. Una matrícula solo se registra si el curso tiene cupos disponibles.
- **Servicio de Cupos (gRPC):** consultar un curso y sus cupos disponibles, listar los cursos ofertados, y ocupar o liberar un cupo para reflejar una matrícula o su retiro.
- **API REST versionada** bajo `/v1`, con semántica HTTP correcta y errores en formato JSON.
- **Contratos formales:** OpenAPI para la API REST y Protocol Buffers para el servicio gRPC.
- **Infraestructura:** todo el sistema debe funcionar con `docker compose up`.
- **Seguridad:** autenticación en la API REST.
- **Resiliencia:** comportamiento predecible cuando el servicio gRPC no responde.

## 1.2 Restricciones identificadas

| Restricción | Descripción |
|---|---|
| **Bases de datos separadas** | Ningún servicio puede acceder directamente a la base de datos de otro (T5). |
| **Comunicación por red** | La interacción entre servicios implica latencia, fallos y particiones de red. |
| **API pública versionada** | Los endpoints deben estar bajo `/v1` con contratos formales (T2, T3). |
| **Autenticación obligatoria** | Toda operación sobre recursos de estudiantes y matrículas requiere autenticación (T6). |
| **Resiliencia ante fallas** | La API debe responder de forma razonable ante la indisponibilidad de Cupos (T7). |
| **Todo dockerizado** | Cada servicio en su contenedor; un solo comando levanta el sistema completo (T1). |
| **Contratos explícitos** | OpenAPI y `.proto` versionados en el repositorio (T3). |

## 1.3 Qué se decidió construir

Se construyó una solución deliberadamente acotada en dos microservicios:

- **Matrículas** (API REST en FastAPI): gestiona estudiantes y matrículas en su propia base SQLite. Expone endpoints bajo `/v1/`. Para verificar disponibilidad, delega al servicio Cupos mediante gRPC. Usa Redis para caché e idempotencia.
- **Cupos** (servicio gRPC): gestiona cursos y contadores de cupos en su propia base SQLite. Expone cuatro RPCs: `ConsultarCurso`, `ListarCursos`, `OcuparCupo` y `LiberarCupo`.
- **Redis** (infraestructura compartida): provee caché cache-aside para consultas de disponibilidad y almacén de claves de idempotencia.

No se intenta introducir una transacción distribuida. La decisión de ocupar un cupo se mantiene atómica dentro del servicio Cupos, y la API informa con precisión los errores recuperables.

---

# 2. Diseño de la solución

## 2.1 Diagrama de arquitectura

<table>
<tr><td colspan="3" style="background-color:#1a3a6b;color:white;text-align:center;font-weight:bold;padding:8px;font-size:11pt;">Cliente HTTP</td></tr>
<tr><td colspan="3" style="text-align:center;padding:4px;font-size:9pt;">(navegador / Postman / script)</td></tr>
<tr><td colspan="3" style="text-align:center;padding:6px;font-size:9pt;border-bottom:1px solid #ccc;">REST /v1 &middot; Bearer Token &middot; HTTPS</td></tr>
<tr><td colspan="3" style="background-color:#1a3a6b;color:white;text-align:center;font-weight:bold;padding:8px;font-size:11pt;">Matrículas <span style="font-weight:normal;">(contenedor, puerto 8000)</span></td></tr>
<tr><td style="padding:6px;border:1px solid #999;font-size:9pt;">FastAPI<br/>Endpoints /v1/<br/>estudiantes, /v1/matriculas</td><td style="padding:6px;border:1px solid #999;font-size:9pt;">Middleware<br/>Bearer Auth<br/>OpenAPI</td><td style="padding:6px;border:1px solid #999;font-size:9pt;">SQLite:<br/>estudiantes,<br/>matriculas</td></tr>
<tr><td colspan="3" style="text-align:center;padding:6px;font-size:9pt;border-bottom:1px solid #ccc;">gRPC / protobuf &middot; Canal reutilizable &middot; Deadline 2s</td></tr>
<tr><td colspan="3" style="background-color:#1a3a6b;color:white;text-align:center;font-weight:bold;padding:8px;font-size:11pt;">Cupos <span style="font-weight:normal;">(contenedor, puerto 50051)</span></td></tr>
<tr><td colspan="3" style="padding:6px;border:1px solid #999;font-size:9pt;">gRPC Server<br/>RPCs: ConsultarCurso, ListarCursos,<br/>OcuparCupo, LiberarCupo<br/>SQLite: cursos (id, nombre, cupos_totales,<br/>cupos_disponibles)</td></tr>
</table>

<br/>

<table>
<tr><td colspan="2" style="background-color:#1a3a6b;color:white;text-align:center;font-weight:bold;padding:8px;font-size:11pt;">Redis <span style="font-weight:normal;">(contenedor, puerto 6379)</span></td></tr>
<tr><td colspan="2" style="padding:6px;border:1px solid #999;font-size:9pt;">Cache-aside (TTL 30s) &middot; Idempotency-Key (24h) &middot; Bearer token</td></tr>
</table>

## 2.2 Descomposición en servicios

| Servicio | Protocolo externo | Protocolo interno | Almacén | Responsabilidades |
|---|---|---|---|---|
| **Matrículas** | REST/JSON (`/v1`) | gRPC cliente | SQLite (`matriculas.db`) | Crear/consultar/listar estudiantes; crear/consultar/listar/revertir matrículas; validar disponibilidad |
| **Cupos** | gRPC/protobuf | — | SQLite (`cupos.db`) | Consultar cursos; listar cursos; ocupar y liberar cupos |
| **Redis** | — | — | In-memory | Caché de disponibilidad; almacén de idempotencia; token de autenticación |

### Flujo de una matrícula

1. El cliente envía `POST /v1/matriculas` con `estudiante_id` y `curso_id`, incluyendo el header `Authorization: Bearer <token>`.
2. El middleware de Matrículas valida el token Bearer.
3. El servicio verifica que el estudiante existe en su base SQLite.
4. Consulta la disponibilidad del curso en Cupos vía gRPC (`ConsultarCurso`). El resultado se cachea en Redis con TTL de 30 segundos.
5. Solicita a Cupos que ocupe un cupo (`OcuparCupo`). Si no hay cupos, Cupos responde `FAILED_PRECONDITION`, que Matrículas traduce a HTTP 409.
6. Si `OcuparCupo` tiene éxito, persiste la matrícula en su base SQLite y elimina la caché de disponibilidad del curso.
7. Si se proporciona una `Idempotency-Key`, se almacena la respuesta en Redis por 24 horas para evitar operaciones duplicadas.

### Flujo de una reversión

1. El cliente envía `POST /v1/matriculas/{id}/revertir`.
2. El servicio valida que la matrícula existe y no está ya revertida.
3. Llama a `LiberarCupo` en Cupos, que incrementa el contador de cupos disponibles.
4. Cambia el estado de la matrícula a `revertida` en su base SQLite.
5. Invalida la caché de disponibilidad del curso.

## 2.3 Justificación de las fronteras

La separación entre Matrículas y Cupos responde a tres criterios fundamentales:

**1. Propiedad de datos.** Cupos es la fuente de verdad de la oferta académica y sus contadores. Matrículas es la fuente de verdad de los datos personales y el historial de inscripciones. Ningún servicio escribe en el almacén del otro (ADR-001). La única duplicación permitida es el identificador del curso dentro de una matrícula, nunca una copia administrable de los cupos.

**2. Independencia de despliegue.** Cada servicio evoluciona a su propio ritmo. Un cambio en el esquema de cupos no requiere redesplegar Matrículas, y viceversa. La frontera de servicio permite escalar o reemplazar Cupos sin exponer su base de datos.

**3. Responsabilidad de negocio.** La lógica de disponibilidad es atómica dentro de Cupos: solo ese servicio puede decidir si un cupo debe ocuparse o liberarse. Matrículas actúa como orquestador, pero la decisión definitiva sobre capacidad reside en el dueño del recurso.

El costo aceptado es que una operación de negocio atraviesa la red. Si `OcuparCupo` tiene éxito pero la persistencia local de Matrículas falla, queda una discrepancia que requeriría conciliación. Se acepta este riesgo para evitar transacciones distribuidas; en producción se añadiría una reserva identificada con proceso de compensación.

---

# 3. ADRs (D1 a D4)

---

## ADR-001 — D1: Frontera entre Cupos y Matrículas

**Estado:** Aceptada

### Contexto

AprendeMás necesita impedir sobrecupos, pero Cupos y Matrículas tienen propietarios y ritmos de cambio distintos. Cupos es la fuente de verdad de la oferta; Matrículas conserva datos personales e historial. Ningún servicio puede escribir en el almacén del otro.

### Alternativas consideradas

- **Monolito con una base compartida:** simplifica una transacción local, pero acopla equipos, despliegues y esquemas.
- **Dos servicios con una base compartida:** separa procesos, pero no propiedad de datos; una modificación al esquema puede romper ambos.
- **Dos servicios y base por servicio:** mantiene la frontera, a costa de una llamada remota y consistencia no distribuida.

### Decisión

Se eligió la tercera opción. Cupos posee `Curso` y los contadores; Matrículas posee `Estudiante` y `Matrícula`. Solo se duplica el identificador del curso dentro de una matrícula, no la disponibilidad. La separación permite escalar o reemplazar Cupos sin exponer su base.

### Consecuencias

La matrícula cruza la red y puede fallar después de ocupar un cupo antes de persistir localmente. Se acepta ese riesgo para evitar transacciones distribuidas; producción añadiría reserva con identificador de operación y conciliación. Si Cupos requiere datos personales, esta frontera debe revisarse.

---

## ADR-002 — D2: REST público y gRPC interno

**Estado:** Aceptada

### Contexto

La API será consumida por personal y un eventual portal web, mientras Matrículas consulta Cupos con frecuencia en una red interna. Se necesita un contrato entendible para clientes heterogéneos y uno tipado para el vínculo interno.

### Alternativas consideradas

- **REST/JSON para todo:** fácil de inspeccionar, pero sin stubs generados ni streaming nativo.
- **gRPC para todo:** eficiente y tipado, pero navegador y herramientas externas requieren gateway o cliente adicional.
- **REST externo y gRPC interno:** interoperabilidad en el borde y contrato binario generado entre servicios.

### Decisión

Se elige REST/JSON bajo `/v1` hacia afuera y gRPC/protobuf internamente. El experimento local obtuvo 39 bytes para `Curso` protobuf frente a 94 bytes JSON. `ListarCursos` es *server streaming*: Cupos produce un curso por vez, sin construir una lista completa al crecer el catálogo.

### Justificación del modo de invocación

Se utiliza **unary-unary síncrono** para `ConsultarCurso`, `OcuparCupo` y `LiberarCupo`. El cliente Matrículas necesita el resultado inmediato de cada llamada para continuar su lógica de negocio: no puede persistir una matrícula sin confirmación de que el cupo se ocupó, ni liberar un cupo sin saber que la reversión se procesó. El patrón unary-unary es el más directo para este caso de solicitud-respuesta donde el resultado se necesita antes de proseguir.

`ListarCursos` usa **server streaming** porque el catálogo puede crecer y el cliente necesita iterar sobre todos los cursos sin esperar a que se construya una lista completa en memoria. El streaming permite procesar cada curso a medida que llega.

### Consecuencias

Hay dos tecnologías, contratos y herramientas de depuración. OpenAPI y `.proto` se versionan juntos. Si un cliente externo requiere streaming se evaluará gRPC-Web, no se expondrá directamente el puerto interno.

---

## ADR-003 — D3: Contrato explícito y evolución compatible

**Estado:** Aceptada

### Contexto

Los contratos tienen consumidores independientes y deben evolucionar sin que un despliegue de servidor rompa a los clientes anteriores.

### Alternativas consideradas

- **Sin versión explícita:** menos rutas, pero un cambio incompatible es ambiguo y riesgoso.
- **Cambiar `/v1` en sitio y reutilizar tags protobuf:** rápido, pero rompe clientes aún en la representación previa.
- **Versionado REST por ruta y evolución aditiva protobuf:** permite migración gradual; requiere disciplina documental.

### Decisión

REST usa `/v1`; un cambio incompatible crea `/v2` y se anuncia con retiro. En protobuf se agregan campos con nuevos números, nunca se renumeran ni reutilizan tags eliminados; los consumidores previos ignoran campos desconocidos. Una futura `descripcion = 5` es compatible, pero renumerar `cupos_disponibles` no lo es.

### Consecuencias

Durante la migración se mantienen representaciones y se documentan consumidores y fecha de deprecación. El CI debe regenerar stubs y ejecutar pruebas de contrato antes de publicar un proto nuevo.

---

## ADR-004 — D4: Fallas y tiempos de espera de Cupos

**Estado:** Aceptada

### Contexto

Matrículas depende de Cupos para decidir una matrícula. Una caída o lentitud no puede generar una traza HTTP ni permitir matricular sin validar disponibilidad.

### Alternativas consideradas

- **Esperar sin deadline:** maximiza intentos exitosos, pero agota hilos bajo una dependencia lenta.
- **Aceptar con caché obsoleta:** conserva disponibilidad, pero puede sobrepasar la capacidad de la sala.
- **Fail fast con deadline y error explícito:** protege al llamador, sacrificando disponibilidad temporal.

### Decisión

El canal gRPC reutilizable usa deadline de 2 segundos. `UNAVAILABLE` se traduce a HTTP 503 y `DEADLINE_EXCEEDED` a 504, ambos con `application/problem+json`, permitiendo reintento. Redis acelera consultas, pero `OcuparCupo` sigue siendo la decisión atómica del dueño de cupos.

### Consecuencias

Una falla recuperable puede rechazar temporalmente una matrícula que podría completar más tarde. El cliente debe reintentar con `Idempotency-Key`; la demo debe detener Cupos y observar el 503.

---

# 4. Experimento: Serialización protobuf vs JSON (Competencia 6)

## 4.1 Hipótesis

La representación binaria Protocol Buffers de un mensaje `Curso` utiliza menos bytes y un tiempo de serialización significativamente menor que su equivalente en JSON, manteniendo los mismos datos.

## 4.2 Método

Se creó un objeto `Curso` protobuf con los campos `id="ARQ-101"`, `nombre="Arquitectura de Sistemas"`, `cupos_totales=40`, `cupos_disponibles=12`. Se construyó un diccionario JSON equivalente con las mismas claves y valores. El experimento ejecuta 10 series de 10.000 serializaciones por formato, midiendo con `time.perf_counter_ns()` el tiempo de cada serialización y `len()` del resultado.

**Variables controladas:** mismo objeto, mismo proceso Python 3.14, mismo hardware, 10.000 serializaciones por serie.

**Script:** `docs/experimento_serializacion.py`

## 4.3 Datos y tabla de resultados

| Formato | Tamaño (bytes) | Media (ns/op) | Desviación estándar (ns) |
|---------|:--------------:|:-------------:|:------------------------:|
| Protobuf | 39 | 238 | ± 72 |
| JSON compacto | 94 | 3.770 | ± 273 |

## 4.4 Análisis

- **Tamaño:** protobuf ocupa **39 bytes** frente a **94 bytes** de JSON. Esto representa una reducción del **58,5 %** en el tamaño del mensaje.
- **Velocidad:** protobuf serializa en **238 ns/op** frente a **3.770 ns/op** de JSON, siendo aproximadamente **15,8 veces más rápido**.
- **Consistencia:** la desviación estándar de protobuf (72 ns) es proporcionalmente menor que la de JSON (273 ns), indicando mayor estabilidad en el rendimiento.

## 4.5 Conclusiones

Los datos respaldan la hipótesis: protobuf es significativamente más eficiente en tamaño y velocidad de serialización que JSON para el mismo mensaje `Curso`. Esto justifica el uso de protobuf para la comunicación interna entre servicios (Matrículas -> Cupos), donde la serialización ocurre frecuentemente en cada solicitud de disponibilidad y ocupación de cupos.

**Limitaciones del experimento:** no mide latencia de red, deserialización, compresión gzip, concurrencia ni rendimiento entre lenguajes distintos. El script permite repetir el procedimiento exacto si cambia el hardware o el runtime.

---

# 5. Consideraciones de contexto (Competencia 2)

## 5.1 Factor elegido: Privacidad de datos estudiantiles

El factor de contexto seleccionado es la **privacidad de los datos de los estudiantes**. En el dominio educativo, los nombres, correos electrónicos y registros de inscripción son datos personales que requieren protección especial.

## 5.2 Cómo influyó en el diseño

**1. Separación de bases de datos.** La decisión de que cada servicio tenga su propia base de datos (ADR-001) se vio fuertemente influenciada por la privacidad. El servicio Cupos, que gestiona la oferta académica, no necesita acceder a los nombres ni correos de los estudiantes. Al separar las bases, se limita la exposición de datos personales: Cupos solo ve identificadores de cursos y contadores de disponibilidad, mientras que Matrículas es el único repositorio de información personal.

**2. Autenticación Bearer.** Toda la API REST requiere un token Bearer para acceder a recursos de estudiantes y matrículas. Esto asegura que solo personal autorizado de AprendeMás pueda crear matrículas, consultar datos personales o revertir inscripciones. El token se declara explícitamente en el contrato OpenAPI y se valida en un middleware antes de enrutar cualquier petición.

**3. Errores sin trazas.** Los mensajes de error del sistema no incluyen stack traces ni información interna de implementación. Se devuelve `application/problem+json` con `type`, `title`, `status` y `detail` genéricos, siguiendo RFC 9457. Esto evita que un error exponga la estructura interna de las bases de datos o las dependencias del sistema a clientes no autorizados.

**4. Frontera de servicio.** La separación entre Cupos y Matrículas no solo es una decisión arquitectónica, sino una decisión de privacidad. Cada servicio expone únicamente la información mínima necesaria a través de sus contratos. Cupos nunca recibe datos personales; solo recibe un identificador de curso y devuelve disponibilidad.

**5. Costo operacional.** La elección de privacidad tiene un costo: tres contenedores más Redis, comunicación por red entre servicios y complejidad de gestión de tokens. Se justifica porque la protección de datos personales es un requisito fundamental del dominio educativo, y Redis además cumple funciones de caché e idempotencia que justifican su presencia independiente.

---

# 6. Instrucciones de ejecución

## 6.1 Requisitos previos

- Docker Desktop instalado y en ejecución.
- Docker Compose disponible (integrado en Docker Desktop o instalado por separado).

## 6.2 Levantar el sistema

```powershell
docker compose up --build
```

Este comando construye y levanta los tres contenedores:

| Contenedor | Imagen | Puerto | Función |
|---|---|:---:|---|
| `cupos` | Python 3.12-slim | 50051 | Servicio gRPC de Cupos |
| `matriculas` | Python 3.12-slim | 8000 | API REST de Matrículas |
| `redis` | redis:7-alpine | 6379 | Caché e idempotencia |

## 6.3 Verificar el funcionamiento

La API REST está disponible en `http://localhost:8000`. La documentación interactiva de Swagger está en `http://localhost:8000/docs`. El contrato OpenAPI se sirve en `http://localhost:8000/openapi.json`.

## 6.4 Ejemplos de uso

```powershell
$headers = @{ Authorization = 'Bearer desarrollo-seguro' }

# Crear un estudiante
$estudiante = Invoke-RestMethod http://localhost:8000/v1/estudiantes -Method Post -Headers $headers -ContentType application/json -Body '{"nombre":"Ana Perez","email":"ana@example.com"}'

# Matricular al estudiante en un curso
$matricula = Invoke-RestMethod http://localhost:8000/v1/matriculas -Method Post -Headers $headers -ContentType application/json -Body "{\"estudiante_id\":\"$($estudiante.id)\",\"curso_id\":\"ARQ-101\"}"

# Consultar una matrícula
Invoke-RestMethod "http://localhost:8000/v1/matriculas/$($matricula.id)" -Method Get -Headers $headers

# Revertir la matrícula (libera el cupo)
Invoke-RestMethod "http://localhost:8000/v1/matriculas/$($matricula.id)/revertir" -Method Post -Headers $headers

# Listar todos los cursos ofertados
Invoke-RestMethod http://localhost:8000/v1/cursos/ARQ-101 -Method Get -Headers $headers
```

## 6.5 Probar resiliencia

Para demostrar el comportamiento ante fallas de la dependencia:

```powershell
docker compose stop cupos
# Intentar crear una matrícula o consultar un curso
# Se espera una respuesta HTTP 503 con application/problem+json
docker compose start cupos
```

Un deadline agotado se traduce a HTTP 504.

## 6.6 Ejecutar pruebas

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Las pruebas incluyen: ciclo de ocupar/liberar cupo, curso inexistente, contrato gRPC con streaming, y validación de OpenAPI con autenticación Bearer y formato problem+json.

---

# 7. Reflexión final

## 7.1 Qué haríamos distinto

**Reserva durable y conciliación.** La implementación actual acepta el riesgo de que `OcuparCupo` tenga éxito pero la persistencia local falle. En producción, se implementaría un sistema de reserva con identificador de operación y proceso de compensación (saga pattern) para garantizar la consistencia eventual entre los dos servicios.

**Observabilidad.** Se añadió un sistema de métricas (Prometheus) y trazabilidad distribuida (OpenTelemetry) para poder diagnósticar problemas de latencia entre servicios y entender el flujo completo de una matrícula.

**Pruebas de integración en contenedores.** Actualmente las pruebas unitarias usan instancias locales del servicio gRPC. Se implementarían pruebas de integración que levanten contenedores reales de Docker para validar el comportamiento del sistema completo.

**TLS entre servicios.** La comunicación gRPC entre contenedores es insegura (`insecure_channel`). En producción se implementaría mTLS con certificados gestionados por un sistema de secretos.

**Autenticación JWT.** El token de desarrollo es estático. En producción se reemplazaría por JWT firmados con un emisor confiable, incluyendo claims de roles y autorización, y rotación automática de claves.

## 7.2 Qué quedó pendiente

- **Conciliación de fallo parcial:** el caso donde `OcuparCupo` succeede pero el `INSERT` de matrícula falle requiere un mecanismo de compensación automático.
- **Retención de datos:** no se definió una política de retención para datos de estudiantes y matrículas antiguas.
- **Auditoría:** no se implementó un log de auditoría para operaciones de matrícula y reversión.
- **Escalamiento horizontal:** el uso de SQLite no es adecuado para múltiples instancias de Matrículas o Cupos; se requeriría PostgreSQL o MySQL con replicación.
- **Rate limiting:** no se implementó protección contra abuso de la API REST.
- **Health checks avanzados:** el endpoint `/health` es básico; se podría agregar verificación de la conexión a la base de datos y al servicio gRPC.
- **Despliegue continuo:** no se configuró un pipeline de CI/CD que automatice la construcción, pruebas y despliegue de los contenedores.

## 7.3 Balance del diseño

La solución evita la sobreconstrucción y cumple con todos los requisitos funcionales y de arquitectura planteados. La separación de responsabilidades entre servicios, la formalización de contratos, el manejo explícito de fallas y la validación de la eficiencia de protobuf son decisiones que el dominio educativo justifica. Las áreas pendientes son extensiones naturales que surgen al escalar de una demostración a un sistema de producción.

---

# Anexos

## Anexo A: Estructura del repositorio

```
tarea-1/
+--- docker-compose.yml
+--- matriculas/
|   +--- Dockerfile
|   +--- requirements.txt
|   +--- openapi.yaml
|   --- app/
|       +--- __init__.py
|       +--- main.py              # API REST FastAPI
|       +--- database.py          # Conexión SQLite
|       +--- grpc_client.py       # Cliente gRPC a Cupos
|       +--- cupos_pb2.py         # Mensajes protobuf generados
|       --- cupos_pb2_grpc.py    # Servicios gRPC generados
+--- cupos/
|   +--- Dockerfile
|   +--- requirements.txt
|   +--- cupos.proto             # Contrato gRPC
|   --- app/
|       +--- __init__.py
|       +--- server.py            # Servicio gRPC
|       +--- database.py          # Conexión SQLite
|       +--- cupos_pb2.py         # Mensajes protobuf generados
|       --- cupos_pb2_grpc.py    # Servicios gRPC generados
+--- tests/
|   +--- test_cupos.py            # Pruebas del servicio Cupos
|   --- test_contracts.py        # Pruebas de contratos
+--- docs/
|   +--- adr/
|   |   +--- ADR-001-frontera-servicios.md
|   |   +--- ADR-002-rest-grpc.md
|   |   +--- ADR-003-versionado.md
|   |   +--- ADR-004-resiliencia.md
|   |   --- ADR-005-autenticacion.md
|   +--- experimento_serializacion.py
|   +--- informe.md
|   +--- guion-video.md
|   --- generar_informe.py
+--- requirements-dev.txt
--- README.md
```

## Anexo B: Contratos formales

### B.1 OpenAPI (matriculas/openapi.yaml)

La API REST está documentada en `matriculas/openapi.yaml` con la versión 1.0.0. Incluye:
- Seguridad: `bearerAuth` aplicada globalmente.
- Formatos de error: `Problema` siguiendo RFC 9457 (`application/problem+json`).
- Endpoints: `/v1/estudiantes`, `/v1/matriculas`, `/v1/cursos/{curso_id}`.

### B.2 Protocol Buffers (cupos/cupos.proto)

El servicio gRPC está definido en `cupos/cupos.proto` con el package `cupos.v1`:
- `ConsultarCurso(ConsultarCursoRequest) returns (Curso)` — unary-unary
- `ListarCursos(ListarCursosRequest) returns (stream Curso)` — server streaming
- `OcuparCupo(ModificarCupoRequest) returns (Curso)` — unary-unary
- `LiberarCupo(ModificarCupoRequest) returns (Curso)` — unary-unary

## Anexo C: Resultados de pruebas

Las pruebas automatizadas verifican:

| Prueba | Verifica |
|---|---|
| `test_ocupar_y_liberar_cupo` | Ciclo completo de ocupar y liberar cupo; agotamiento de cupos |
| `test_curso_inexistente` | Manejo de curso no encontrado en Cupos |
| `test_grpc_contract_exposes_required_operations` | Presencia de los 4 RPCs y streaming en `ListarCursos` |
| `test_openapi_declares_v1_auth_and_problem_responses` | Bearer Auth, endpoints `/v1`, Problema+JSON |

---

**Documento generado para el proyecto Forma A — Sistema de Gestión de Cursos y Matrículas.**
