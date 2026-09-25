FROM python:3.12-slim
WORKDIR /service
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
ENV HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/data/shortener.db
VOLUME ["/data"]
EXPOSE 8000
CMD ["shortener", "serve"]
