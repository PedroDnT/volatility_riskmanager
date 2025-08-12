# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependency configuration files
# This is done first to leverage Docker's layer caching.
# Dependencies are only re-installed if these files change.
COPY pyproject.toml ./
COPY README.md ./
# Copying README as it's referenced in pyproject.toml

# Copy the rest of the application source code
COPY . .

# Install any needed dependencies specified in pyproject.toml
# The '.' installs the current directory as a package
RUN pip install --no-cache-dir .

# Create a non-root user to run the application
RUN useradd --create-home appuser
USER appuser

# Set the default command to run the application
# This will execute the 'risk-manager' script defined in pyproject.toml
CMD ["risk-manager"]

