# Use official Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install Git, Docker, Node.js, Maven, Terraform, and helpers (for license audit + infra + SonarQube)
# Note: we don't need netcat inside this container (Kafka/ZooKeeper images already include it),
# so we avoid the virtual 'netcat' package that fails to install on some Debian variants.
RUN apt-get update && \
    apt-get install -y git docker.io wget unzip curl && \
    apt-get clean

# Node.js (for npx / license-checker in license_audit)
ENV NODE_VERSION=20
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

# Maven (for mvn license:download-licenses in license_audit)
ENV MAVEN_VERSION=3.9.6
RUN wget https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz && \
    tar -xzf apache-maven-${MAVEN_VERSION}-bin.tar.gz -C /opt && \
    ln -sf /opt/apache-maven-${MAVEN_VERSION}/bin/mvn /usr/local/bin/mvn && \
    rm apache-maven-${MAVEN_VERSION}-bin.tar.gz

# Install Terraform CLI
ENV TERRAFORM_VERSION=1.14.6

RUN wget https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    mv terraform /usr/local/bin/ && \
    rm terraform_${TERRAFORM_VERSION}_linux_amd64.zip

# Install SonarQube scanner CLI (for code analysis agent)
ENV SONAR_SCANNER_VERSION=5.0.1.3006
RUN curl -L -o /tmp/sonar-scanner.zip \
      https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip && \
    unzip /tmp/sonar-scanner.zip -d /opt && \
    ln -sf /opt/sonar-scanner-*/bin/sonar-scanner /usr/local/bin/sonar-scanner && \
    rm /tmp/sonar-scanner.zip

# Copy project files into the container
COPY . /app

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Run the coordinator (Slack gateway + pipeline; no HTTP port, uses Slack Socket Mode)
CMD ["python", "main.py"]
