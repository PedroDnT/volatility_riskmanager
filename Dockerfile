# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependency configuration files
# This is done first to leverage Docker's layer caching.
# Dependencies are only re-installed if these files change.
COPY pyproject.toml ./
COPY README.md ./
COPY requirements.txt ./
# Copying README as it's referenced in pyproject.toml

# Copy the rest of the application source code
COPY . .

# Install any needed dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir .

# Create a non-root user to run the application
RUN useradd --create-home appuser
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Set the default command to run the web application
CMD ["python", "app.py"]
