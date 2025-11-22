FROM python:3.9-slim

WORKDIR /app

# システム依存関係のインストール (必要な場合)
# RUN apt-get update && apt-get install -y ...

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["python", "main.py"]