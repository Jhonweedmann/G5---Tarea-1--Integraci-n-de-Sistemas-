# Guion del video (máximo 8 minutos)

El enunciado usa el dominio de la biblioteca. Las equivalencias para la Forma K son:

| Enunciado | Nuestro sistema |
|---|---|
| Registrar un socio | Crear un estudiante (`POST /v1/estudiantes`) |
| Registrar un préstamo (consulta al Catálogo por gRPC) | Matricular (`POST /v1/matriculas`, que invoca `OcuparCupo` en Cupos) |
| Prestar un libro sin ejemplares | Matricular en `API-201`, que tiene 1 cupo, cuando ya está ocupado |
| Devolver un préstamo | Revertir la matrícula (`POST /v1/matriculas/{id}/revertir`) |
| Apagar el Catálogo | `docker compose stop cupos` |

## Antes de grabar (no se graba)

Dejar las bases vacías y las imágenes construidas, para que `docker compose up` arranque en segundos:

```powershell
docker compose down -v
docker compose build
docker compose --profile demo build
```

Pantalla:

- **Terminal 1:** para `docker compose up`; va a mostrar los logs.
- **Terminal 2:** para los comandos. Cargar la función de ayuda, que muestra el código HTTP y la latencia de cada llamada:

  ```powershell
  . .\scripts\llamar.ps1
  ```

- **Navegador:** con la figura de arquitectura del informe y `http://localhost:8000/docs`, abierto recién cuando la API esté arriba.
- **Letra grande** en las terminales. `Clear-Host` entre escenas.

Hacer un ensayo completo y volver a ejecutar `docker compose down -v` antes de grabar, porque los correos no se pueden repetir.

## Escena 1 · Arquitectura (0:00–0:45)

**Mostrar:** la figura 1 del informe.

**Decir:**

- Dos sistemas que ya existían por separado. Los separamos por bounded context y cada uno tiene su propia base; ninguno toca la del otro.
- REST hacia afuera, porque la usan personas y un futuro portal web. gRPC hacia adentro, porque es tráfico interno de alto volumen y queremos un contrato tipado y compilado.
- La regla de cupo vive en un solo lugar, Cupos. Así se evita el sobrecupo.

## Escena 2 · Levantar el sistema (0:45–1:30)

**Terminal 1:**

```powershell
docker compose up
```

**Terminal 2**, cuando aparezca `Uvicorn running`:

```powershell
docker compose ps
```

```powershell
Llamar GET /health -Token $null
```

**Decir:**

- Todo se levanta con un solo comando: tres contenedores.
- En `docker compose ps` solo Matrículas publica un puerto (8000). Cupos y Redis quedan dentro de la red interna, porque la comunicación con Cupos no la ve el exterior.
- Los stubs gRPC se generan en el build desde el único `cupos.proto`; no hay copias del contrato.

## Escena 3 · Contratos (1:30–2:00)

**Mostrar:** `http://localhost:8000/docs` y, en el editor, `cupos/cupos.proto`.

**Decir:**

- Lo que se ve en `/docs` es el `openapi.yaml` escrito a mano (contract-first), no uno generado desde el código. Versionado en `/v1`, autenticación Bearer declarada en el contrato y errores en formato RFC 9457.
- En el `.proto`, `package cupos.v1`. `ListarCursos` es server streaming porque el catálogo puede crecer; las demás operaciones son unarias.

## Escena 4 · Recorrido por los endpoints (2:00–4:30)

**4.1 Registrar un estudiante (el "socio"):**

```powershell
$ana = Llamar POST /v1/estudiantes @{ nombre = "Ana Perez"; email = "ana@example.com" }
```

> **Decir:** 201 Created, con cabecera `Location` hacia el recurso nuevo.

**4.2 Consultar el curso, que tiene 1 cupo:**

```powershell
Llamar GET /v1/cursos/API-201
```

> **Decir:** esta consulta viaja a Cupos por gRPC (`ConsultarCurso`) y se guarda en Redis por 30 s, solo para lecturas.

**4.3 Matricular (el "préstamo"):**

```powershell
$m = Llamar POST /v1/matriculas @{ estudiante_id = $ana.id; curso_id = "API-201" } -Clave video-1
```

```powershell
$m._links
```

> **Decir:**
> - Matrículas invoca `OcuparCupo` por gRPC, y Cupos verifica y descuenta en una sola operación atómica. La decisión nunca se toma con la caché, porque eso reabriría el sobrecupo.
> - La respuesta trae `_links` (HATEOAS): como la matrícula está activa, ofrece la acción `revertir`.

**4.4 Reintento con la misma clave:**

```powershell
Llamar POST /v1/matriculas @{ estudiante_id = $ana.id; curso_id = "API-201" } -Clave video-1
```

> **Decir:** 200 y la misma matrícula. Es el `Idempotency-Key`: si el cliente pierde la respuesta y reintenta, no se ocupa un segundo cupo.

**4.5 Curso sin cupos (el "libro sin ejemplares"):**

```powershell
$beto = Llamar POST /v1/estudiantes @{ nombre = "Beto Soto"; email = "beto@example.com" }
```

```powershell
Llamar POST /v1/matriculas @{ estudiante_id = $beto.id; curso_id = "API-201" }
```

> **Decir:** rechazo 409 "No hay cupos disponibles". Cupos responde `FAILED_PRECONDITION` por gRPC y la API lo traduce a 409, en formato `application/problem+json`.

**4.6 Revertir (la "devolución"):**

```powershell
Llamar POST "/v1/matriculas/$($m.id)/revertir"
```

```powershell
Llamar GET /v1/cursos/API-201
```

> **Decir:**
> - `LiberarCupo` por gRPC: la matrícula queda `revertida` y ya no ofrece el enlace `revertir`.
> - El curso vuelve a tener 1 cupo de inmediato, porque cada escritura invalida la caché.

**4.7 Seguridad (opcional, ~20 s):**

```powershell
Llamar GET /v1/estudiantes -Token $null
```

```powershell
Llamar POST /v1/estudiantes @{ nombre = "Otro"; email = "otro@example.com" } -Token solo-lectura
```

> **Decir:** 401 cuando no sabemos quién llama; 403 cuando el token es válido pero de solo lectura.

## Escena 5 · Modo de falla: apagar Cupos (4:30–6:45)

Dejar **escrito de antemano** el comando de matrícula de abajo (flecha arriba), para ejecutarlo apenas se detenga Cupos. La fase de 504 dura solo 20 s.

```powershell
docker compose stop cupos
```

```powershell
Llamar POST /v1/matriculas @{ estudiante_id = $beto.id; curso_id = "ARQ-101" }
```

Repetir la matrícula varias veces seguidas (flecha arriba + Enter) hasta que cambie de 504 a 503.

> **Decir:**
> - Primero responde **504** y cada llamada tarda **~2000 ms**: es el deadline de 2 s que pusimos a la llamada gRPC. Sin deadline, Matrículas se quedaría colgada esperando a Cupos.
> - Durante unos 20 s gRPC sigue intentando conectar; ese es su tiempo mínimo por intento de conexión. Mientras tanto las llamadas esperan hasta el deadline.
> - Después, el canal marca a Cupos como caído y la API responde **503 en milisegundos**. Lo medimos en 5 repeticiones: el cambio ocurre siempre a los 20,0 s.
> - Ambos códigos están en el contrato y son reintentables con `Idempotency-Key`.
> - Lo importante: **no matriculamos a ciegas**. Preferimos sacrificar disponibilidad antes que permitir un sobrecupo.

Mostrar que no se creó ninguna matrícula (debe seguir en 1, la de Ana, revertida):

```powershell
(Llamar GET /v1/matriculas).total
```

Recuperación:

```powershell
docker compose start cupos
```

Esperar ~5 s:

```powershell
Llamar POST /v1/matriculas @{ estudiante_id = $beto.id; curso_id = "ARQ-101" }
```

> **Decir:** 201. El sistema se recupera solo en ~4 s, sin reiniciar Matrículas.

## Escena 6 · Interoperabilidad (opcional, 6:45–7:15)

```powershell
docker compose --profile demo run --rm cupos-node-client
```

> **Decir:** un cliente Node.js consume el mismo `cupos.proto` sin modificar el servidor Python. El contrato es independiente del lenguaje.

## Escena 7 · Cierre (7:15–7:50)

**Decir:**

- Cada decisión tiene su costo aceptado, documentado en los ADR.
- Dos servicios cuestan una llamada remota y no tener una transacción entre ambos.
- gRPC agrega un segundo contrato.
- El fail-fast rechaza matrículas mientras Cupos está caído.
- Los experimentos del informe respaldan las decisiones con datos: protobuf pesa el 40% de JSON (0,73–0,85 con gzip), y medimos la secuencia 504 → 503 al caer Cupos.

## Si algo sale mal durante la grabación

- **Aparece 409 "Correo duplicado":** quedaron datos del ensayo. Ejecutar `docker compose down -v` y `docker compose up`, y volver a cargar `. .\scripts\llamar.ps1`.
- **Solo se ve 503 al apagar Cupos:** pasaron más de 20 s antes de la primera llamada. Ejecutar `docker compose start cupos`, esperar ~5 s y repetir la escena 5 más rápido.
- **`$ana` o `$beto` están vacíos:** se cerró la terminal 2 o se recargó el script. Volver a crear los estudiantes con otros correos.
