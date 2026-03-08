FROM python:3.11-slim

WORKDIR /workspace

RUN useradd -m appuser
USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY sandbox/mini_bash_agent.py /workspace/mini_bash_agent.py

CMD ["python", "mini_bash_agent.py", "Inspect PDFs and generate quiz outputs", "--workspace", "/workspace"]
