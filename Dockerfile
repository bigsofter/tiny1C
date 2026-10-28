# syntax=docker/dockerfile:1
# Сетевой режим tiny1C: MCP поверх streamable HTTP для сервисов во внутренней сети (mcp/httpd.py).
#
# В образ входит КОД сервера и ВСТРОЕННАЯ КОПИЯ набора (tracks/, manifest.json) на момент сборки.
# Дальше сервис сам подтягивает знания из git в том /data и подменяет их после проверки; код из git
# не исполняется никогда — новый код только новым образом. Поэтому образ собирается с закреплённой
# ревизии репозитория и так же закрепляется в compose того, кто его запускает.
#
# git нужен для подгрузки знаний (ls-remote, fetch, archive); wget — для healthcheck.
FROM python:3.12-alpine
RUN apk add --no-cache git wget
WORKDIR /app
COPY mcp/ mcp/
COPY scripts/manifest.py scripts/manifest.py
COPY manifest.json README.md LICENSE LICENSE-CONTENT ./
COPY tracks/ tracks/
COPY tools/ tools/
RUN mkdir -p /data && chown nobody:nobody /data \
    && python3 -m compileall -q mcp scripts \
    && python3 scripts/manifest.py --проверить
ENV TINY1C_DATA=/data \
    TINY1C_HTTP_ADDR=0.0.0.0:8111 \
    TINY1C_REPO_URL=https://github.com/bigsofter/tiny1C \
    TINY1C_BRANCH=main \
    TINY1C_SYNC_INTERVAL=300 \
    TINY1C_TOOLS=instructions \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8111
USER nobody:nobody
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8111/healthz >/dev/null || exit 1
# TINY1C_SERVICE_TOKEN задаёт запускающий; без него сервис не стартует.
ENTRYPOINT ["python3", "mcp/httpd.py"]
