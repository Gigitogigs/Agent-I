FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution and installation
RUN pip install uv

# Copy the requirements files
COPY pyproject.toml requirements.txt uv.lock* ./

# Install dependencies using uv
RUN uv pip install --system -r requirements.txt

# Copy the rest of the application
COPY . .

# Set Python path so imports work correctly
ENV PYTHONPATH=/app
