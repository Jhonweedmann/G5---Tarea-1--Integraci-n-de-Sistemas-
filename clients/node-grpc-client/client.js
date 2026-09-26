/**
 * Cliente gRPC en Node.js para el servicio Cupos.
 *
 * Requisito opcional O5 — "Segundo cliente gRPC en otro lenguaje".
 * Este cliente NO forma parte del sistema en producción (Matrículas ya tiene
 * su propio cliente en Python, en matriculas/app/grpc_client.py). Su único
 * propósito es demostrar que el contrato cupos.proto es interoperable:
 * cualquier lenguaje con soporte gRPC puede consumir el mismo servicio de
 * Cupos sin cambiar una línea del servidor.
 *
 * A diferencia del cliente Python (que usa código generado con protoc:
 * cupos_pb2.py / cupos_pb2_grpc.py), este cliente carga el .proto en tiempo
 * de ejecución con @grpc/proto-loader, sin paso de compilación previo.
 * Es la forma más común de consumir gRPC en Node.js y sirve como segunda
 * evidencia de interoperabilidad: ni siquiera hace falta generar código
 * para hablar con el mismo servicio.
 *
 * Uso (dentro de la red de docker-compose, porque Cupos no publica su puerto):
 *   docker compose --profile demo run --rm cupos-node-client
 *
 * Lee el mismo contrato que el servidor (cupos/cupos.proto); no hay copia local.
 */

const path = require("path");
const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");

const PROTO_PATH = process.env.PROTO_PATH || path.join(__dirname, "..", "..", "cupos", "cupos.proto");
const TARGET = process.argv[2] || process.env.CUPOS_GRPC_TARGET || "localhost:50051";

function crearCliente() {
  const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
    keepCase: true,
    longs: Number,
    enums: String,
    defaults: true,
    oneofs: true,
  });

  const proto = grpc.loadPackageDefinition(packageDefinition).cupos.v1;
  return new proto.Cupos(TARGET, grpc.credentials.createInsecure());
}

function listarCursos(client) {
  return new Promise((resolve, reject) => {
    const cursos = [];
    const call = client.ListarCursos({});
    call.on("data", (curso) => cursos.push(curso));
    call.on("end", () => resolve(cursos));
    call.on("error", (err) => reject(err));
  });
}

function consultarCurso(client, cursoId) {
  return new Promise((resolve, reject) => {
    client.ConsultarCurso({ curso_id: cursoId }, (err, response) => {
      if (err) return reject(err);
      resolve(response);
    });
  });
}

function ocuparCupo(client, cursoId) {
  return new Promise((resolve, reject) => {
    client.OcuparCupo({ curso_id: cursoId }, (err, response) => {
      if (err) return reject(err);
      resolve(response);
    });
  });
}

function liberarCupo(client, cursoId) {
  return new Promise((resolve, reject) => {
    client.LiberarCupo({ curso_id: cursoId }, (err, response) => {
      if (err) return reject(err);
      resolve(response);
    });
  });
}

async function main() {
  console.log(`Conectando al servicio Cupos en ${TARGET} (gRPC, Node.js)...\n`);
  const client = crearCliente();

  console.log("=== ListarCursos (server streaming) ===");
  const cursos = await listarCursos(client);
  cursos.forEach((c) =>
    console.log(`  ${c.id} — ${c.nombre}: ${c.cupos_disponibles}/${c.cupos_totales} disponibles`)
  );

  if (cursos.length === 0) {
    console.log("  (sin cursos; nada más que probar)");
    return;
  }

  const cursoId = cursos[0].id;

  console.log(`\n=== ConsultarCurso("${cursoId}") ===`);
  console.log(" ", await consultarCurso(client, cursoId));

  console.log(`\n=== OcuparCupo("${cursoId}") ===`);
  console.log(" ", await ocuparCupo(client, cursoId));

  console.log(`\n=== LiberarCupo("${cursoId}") ===`);
  console.log(" ", await liberarCupo(client, cursoId));

  console.log(
    "\nLos 4 RPC definidos en cupos.proto respondieron correctamente desde un cliente Node.js,\n" +
      "sin modificar el servidor Python de Cupos: el contrato es interoperable entre lenguajes."
  );
}

main().catch((err) => {
  console.error("Error al invocar el servicio Cupos:", err.message || err);
  process.exit(1);
});
