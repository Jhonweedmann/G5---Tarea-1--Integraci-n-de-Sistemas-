# Cliente gRPC en Node.js — Servicio Cupos (O5)
## Requisitos

- Node.js 18 o superior
- El servicio Cupos corriendo y accesible (localmente en `localhost:50051`, o `cupos:50051` si se ejecuta dentro de la red de `docker-compose`)

## Cómo ejecutarlo

```bash
cd clients/node-grpc-client
npm install
node client.js                 # usa localhost:50051 por defecto
node client.js cupos:50051     # o el host:puerto que corresponda
```

## Qué hace el script

Contra el servicio Cupos real, ejecuta en orden los 4 RPC definidos en `cupos.proto`:

1. `ListarCursos` (server streaming) — imprime todos los cursos y su disponibilidad.
2. `ConsultarCurso` — consulta el primer curso de la lista.
3. `OcuparCupo` — ocupa un cupo de ese curso.
4. `LiberarCupo` — lo libera de vuelta, dejando el estado como estaba.

## Verificación realizada

Este cliente fue probado end-to-end contra una instancia real del servidor `cupos/app/server.py` (Python), sin modificar el servidor. Salida real obtenida:

```
=== ListarCursos (server streaming) ===
  API-201 — Integracion de APIs: 1/1 disponibles
  ARQ-101 — Arquitectura de Sistemas: 2/2 disponibles
  DAT-110 — Fundamentos de Datos: 3/3 disponibles

=== ConsultarCurso("API-201") ===
  { id: 'API-201', nombre: 'Integracion de APIs', cupos_totales: 1, cupos_disponibles: 1 }

=== OcuparCupo("API-201") ===
  { id: 'API-201', nombre: 'Integracion de APIs', cupos_totales: 1, cupos_disponibles: 0 }

=== LiberarCupo("API-201") ===
  { id: 'API-201', nombre: 'Integracion de APIs', cupos_totales: 1, cupos_disponibles: 1 }
```

## Nota técnica: `keepCase: true`

El loader se configura con `keepCase: true` para que los nombres de campo se mantengan exactamente como están en el `.proto` (`curso_id`, `cupos_totales`, `cupos_disponibles`), en vez de convertirlos a camelCase (`cursoId`, `cuposTotales`). Esto es intencional: mantiene el cliente Node.js alineado 1:1 con el mismo contrato que usa el cliente Python, sin una capa de traducción de nombres que pueda esconder un descalce de campos entre lenguajes.
