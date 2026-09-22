# Guion de video (máximo 8 minutos)

1. **0:00–1:00** — Ejecutar `docker compose up --build`; mostrar los tres servicios arriba.
2. **1:00–4:00** — Crear estudiante, matricular en `ARQ-101`, consultar curso y mostrar la baja; revertir y mostrar el alza. Intentar una segunda matrícula sobre `API-201` sin cupos y mostrar el 409.
3. **4:00–6:30** — Ejecutar `docker compose stop cupos`; repetir una consulta o creación y mostrar respuesta 503 `problem+json`.
4. **6:30–8:00** — Mostrar proto, OpenAPI, ADR y explicar REST externo/gRPC interno, deadline y bases separadas.
