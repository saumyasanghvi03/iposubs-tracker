# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# We use --no-cache-dir to reduce image size
# WeasyPrint might have system dependencies that need to be installed.
# Common ones include Pango, Cairo, and GDK-PixBuf.
# For a Debian/Ubuntu based system (like python:3.9-slim), you might need:
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# If more specific errors occur during WeasyPrint usage, other libraries like
# libpangoft2-1.0-0 or fonts might be needed.

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the working directory
COPY . .

# Make port 8080 available to the world outside this container
# Cloud Run expects the container to listen on the port defined by the PORT env var (defaults to 8080)
EXPOSE 8080

# Define environment variable for the PORT
# Gunicorn will bind to this port. Cloud Run automatically sets this.
ENV PORT 8080

# Run app.py when the container launches using Gunicorn
# The number of workers can be adjusted based on the instance size.
# For Cloud Run, it's often recommended to have (2 * num_cores) + 1 workers.
# A simple default is 2-4 workers for small instances.
# Use 0.0.0.0 to bind to all network interfaces.
CMD ["gunicorn", "--bind", "0.0.0.0:${PORT}", "--workers", "2", "app:app"]
