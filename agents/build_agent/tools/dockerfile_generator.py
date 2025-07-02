def generate_dockerfile(language: str, framework: str) -> str:
    if framework.lower() == "flask":
        return """\
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["python", "main.py"]
"""
    raise ValueError(f"Unsupported framework: {framework}")
