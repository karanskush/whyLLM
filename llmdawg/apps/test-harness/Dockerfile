FROM python:3.11-slim AS runtime

WORKDIR /app

COPY packages/python-sdk /app/packages/python-sdk
COPY apps/test-harness /app/apps/test-harness

RUN pip install --no-cache-dir /app/packages/python-sdk && \
    pip install --no-cache-dir /app/apps/test-harness

EXPOSE 8100

CMD ["uvicorn", "test_harness.main:app", "--host", "0.0.0.0", "--port", "8100"]
