# Use official Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install Git, Docker, and Terraform dependencies
RUN apt-get update && \
    apt-get install -y git docker.io wget unzip && \
    apt-get clean

# Install Terraform CLI
ENV TERRAFORM_VERSION=1.5.7

RUN wget https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    mv terraform /usr/local/bin/ && \
    rm terraform_${TERRAFORM_VERSION}_linux_amd64.zip

# Copy project files into the container
COPY . /app

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Expose the Flask port
EXPOSE 5001

# Run the main app
CMD ["python", "main.py"]
