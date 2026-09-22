FROM python:3.12-slim
WORKDIR /app
COPY cupos/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY cupos ./
RUN python -m grpc_tools.protoc -I. --python_out=app --grpc_python_out=app cupos.proto && sed -i 's/^import cupos_pb2/from . import cupos_pb2/' app/cupos_pb2_grpc.py
ENV PYTHONPATH=/app
CMD ["python", "-m", "app.server"]
