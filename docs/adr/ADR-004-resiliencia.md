# ADR-004 · Fallas de Cupos y de Redis

**Estado:** aceptada

## Contexto

Matrículas depende de Cupos para decidir cada matrícula y de Redis para la caché y la idempotencia. Si Cupos está caído o lento, la API no puede quedarse colgada ni matricular sin validar, porque eso reabriría el sobrecupo. Si Redis cae, la API no debería caerse por una dependencia que es una optimización.

## Alternativas consideradas

- **Esperar sin deadline:** maximiza las matrículas que terminan bien, pero cada petición retiene un hilo mientras Cupos no responde y la lentitud se propaga a Matrículas.
- **Aceptar con la última caché conocida:** mantiene disponible la API, pero puede autorizar una matrícula sobre un cupo que ya no existe, que es justo el sobrecupo que se busca evitar.
- **Fail-fast con deadline y error explícito:** protege al llamador y conserva la corrección del cupo, a cambio de rechazar matrículas mientras Cupos no está.

## Decisión

Fail-fast con un deadline de 2 s por llamada gRPC, sobre un canal reutilizable. Traducción de errores a HTTP:

| gRPC | HTTP |
|---|---|
| `UNAVAILABLE` | 503 |
| `DEADLINE_EXCEEDED` | 504 |
| `NOT_FOUND` | 404 |
| `FAILED_PRECONDITION` | 409 |
| cualquier otro | 502 |

Todas las respuestas de error usan `application/problem+json` con textos fijos, sin detalles internos como direcciones IP. Redis se trata como opcional:

- Si falla la caché, se consulta directamente a Cupos.
- Si falla la idempotencia y el cliente envió `Idempotency-Key`, se responde 503 en vez de arriesgar un duplicado.
- Tras cualquier falla de Redis, Matrículas deja de intentarlo durante 15 s y responde como si no estuviera.

## Justificación

Datos de `docs/experimento_resiliencia.py`: 5 repeticiones, 35 s con Cupos detenido, una consulta por segundo.

- Durante los primeros **20,0 s** (idéntico en las 5 repeticiones) cada llamada agota el deadline y la API responde **504** en 2,01 s (mediana). En ese intervalo gRPC sigue intentando conectar: su tiempo mínimo por intento de conexión es de 20 s (`MIN_CONNECT_TIMEOUT`), y mientras el canal está en `CONNECTING` las llamadas esperan.
- Después, el canal pasa a `TRANSIENT_FAILURE` y las llamadas fallan de inmediato con `UNAVAILABLE`: la API responde **503** en 9 ms (mediana).
- Al reiniciar Cupos, la API vuelve a responder normalmente en 3,4–3,7 s.

El deadline acota la espera a 2 s en la fase en que, sin él, la llamada esperaría el intento de conexión completo. Esa última afirmación es una inferencia de la documentación de gRPC; no se midió sin deadline.

La pausa de Redis también se decidió a partir de una medición. Con el contenedor de Redis detenido, resolver el nombre `redis` tarda entre 4 y 8 s, y el timeout de conexión de 0,5 s no cubre esa espera. Sin la pausa, cada petición sumaba esa demora una o dos veces (hasta 11,7 s observados). Con la pausa, solo la primera petición tras la caída tarda (~7,9 s) y las siguientes responden en 25–40 ms.

## Costo aceptado

- Mientras Cupos no responde, no se puede matricular.
- Durante los primeros 20 s cada petición retiene un hilo durante 2 s, lo que bajo carga alta podría agotar el pool de hilos (no medido).
- Sin Redis, un cliente que usa `Idempotency-Key` recibe 503 aunque Cupos esté sano.
- Mientras Redis siga caído, cada 15 s una petición vuelve a probarlo y paga la espera de DNS. Cuando Redis vuelve, la caché y la idempotencia pueden tardar hasta 15 s en reactivarse.

## Consecuencias

Los clientes deben reintentar los 503 y 504 con la misma `Idempotency-Key`. El resultado depende de cómo cae Cupos: con el contenedor detenido los paquetes no reciben respuesta y se espera el intento de conexión completo. Si solo muriera el proceso dentro de un contenedor vivo, la conexión se rechazaría de inmediato y probablemente se vería 503 desde el inicio (no medido). Para acortar la fase de 504 se podría ajustar la reconexión del canal o agregar un circuit breaker.
