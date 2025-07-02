import os

def detect_language_framework(repo_path: str) -> str:
    if os.path.exists(os.path.join(repo_path, "package.json")):
        return "nodejs"
    if os.path.exists(os.path.join(repo_path, "requirements.txt")):
        with open(os.path.join(repo_path, "requirements.txt")) as f:
            contents = f.read().lower()
            if "django" in contents:
                return "django"
            elif "flask" in contents:
                return "flask"
        return "python"
    return "unknown"

def generate_dockerfile(repo_path: str, framework: str, has_frontend: bool) -> str:
    if has_frontend and framework == "flask":
        return f"""\
# Stage 1: Build frontend
FROM node:18 as frontend-builder
WORKDIR /app
COPY frontend/ frontend/
RUN cd frontend && npm install && npm run build

# Stage 2: Backend with Flask
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-builder /app/frontend/build /app/static
EXPOSE 5000
CMD ["python", "main.py"]
"""
    elif framework == "flask":
        return f"""\
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "main.py"]
"""
    elif framework == "django":
        return f"""\
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
"""
    elif framework == "nodejs":
        return f"""\
FROM node:18
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
"""
    return "# Could not detect framework; please write Dockerfile manually.\n"
