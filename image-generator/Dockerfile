FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY config.py .
COPY utils.py .
COPY generators/ ./generators/

EXPOSE 5000

CMD ["python", "app.py"]