FROM python:3.9-slim

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルのコピー
COPY app.py .

# utilsディレクトリのコピー
COPY utils/ ./utils/

# tabsディレクトリのコピー
COPY tabs/ ./tabs/

# Streamlitのデフォルトポート
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]