# Use official Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install Git and system dependencies
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean

# Copy project files into the container
COPY . /app

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Expose the Flask port
EXPOSE 5001

# Run the main app
CMD ["python", "main.py"]
