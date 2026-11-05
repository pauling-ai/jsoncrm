FROM python:3.12-slim

RUN pip install --no-cache-dir "jsoncrm[web,mcp]==1.0.1"

WORKDIR /crm
EXPOSE 7341

# Default: stdio MCP server (docker run image  → MCP on stdin/stdout)
# Web UI:   docker run -p 7341:7341 image serve
ENTRYPOINT ["jsoncrm"]
CMD ["mcp"]
