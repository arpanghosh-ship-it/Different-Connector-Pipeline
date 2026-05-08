FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN grep -v "python-certifi-win32" /app/requirements.txt > /tmp/requirements_docker.txt \
    && pip install --no-cache-dir -r /tmp/requirements_docker.txt

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
