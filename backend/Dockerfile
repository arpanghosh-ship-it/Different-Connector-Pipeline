# Use an official, lightweight Python 3.12 image 
# (Python 3.12 is chosen based on your __pycache__ cpython-312 files)
FROM python:3.12-slim

# Prevent Python from writing pyc files to disc and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache for dependencies
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create the default storage directory referenced in config.py
RUN mkdir -p /app/storage

# Expose the port Uvicorn will run on
EXPOSE 3005

# Command to start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3005"]