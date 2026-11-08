FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV PORT=8080
EXPOSE 8080
USER nobody
CMD ["mojoanalyzer", "serve", "--host", "0.0.0.0"]
