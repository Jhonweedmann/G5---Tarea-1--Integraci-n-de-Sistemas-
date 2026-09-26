FROM node:20-alpine
WORKDIR /cliente
COPY clients/node-grpc-client/package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY clients/node-grpc-client/client.js ./
COPY cupos/cupos.proto ./cupos.proto
ENV PROTO_PATH=/cliente/cupos.proto
CMD ["node", "client.js", "cupos:50051"]
