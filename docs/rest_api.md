# REST API

The Plant-Imager3 project provides a REST API for interacting with the system programmatically.
This API is used by the web UI and can also be used by custom scripts and applications.

## API Endpoints

The REST API is provided by the FSDB (File System Database) REST API server, which is part of the `plantdb.server` package.
The Plant-Imager3 project uses this API to store and retrieve scan data.

### Starting the API Server

To start the API server for testing purposes, you can use the following command:

```shell
fsdb_rest_api --test
```

For production use, you should configure the API server to use a specific database directory:

```shell
fsdb_rest_api --db-path /path/to/database
```

### Authentication

The API server supports basic authentication.
You can configure users in the server configuration file.

## API Documentation

The complete API documentation is available in the [plantdb documentation](https://romi.github.io/plantdb/).

### Key Endpoints

Here are some of the key endpoints provided by the API:

#### Scans

- `GET /scans`: List all scans
- `GET /scans/{scan_id}`: Get information about a specific scan
- `POST /scans`: Create a new scan
- `DELETE /scans/{scan_id}`: Delete a scan

#### Files

- `GET /scans/{scan_id}/files`: List all files in a scan
- `GET /scans/{scan_id}/files/{file_id}`: Get a specific file
- `POST /scans/{scan_id}/files`: Upload a file to a scan
- `DELETE /scans/{scan_id}/files/{file_id}`: Delete a file from a scan

#### Metadata

- `GET /scans/{scan_id}/metadata`: Get metadata for a scan
- `PUT /scans/{scan_id}/metadata`: Update metadata for a scan

## Using the API

Here's an example of how to use the API with Python:

```python
import requests
import json

# Base URL for the API
base_url = "http://localhost:5000"

# List all scans
response = requests.get(f"{base_url}/scans")
scans = response.json()
print(f"Found {len(scans)} scans")

# Create a new scan
scan_data = {
    "id": "my_scan",
    "metadata": {
        "plant": "Arabidopsis",
        "date": "2023-01-01"
    }
}
response = requests.post(f"{base_url}/scans", json=scan_data)
print(f"Created scan: {response.json()}")

# Upload a file to the scan
with open("image.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{base_url}/scans/my_scan/files", files=files)
print(f"Uploaded file: {response.json()}")
```

## Integration with Plant-Imager3

The Plant-Imager3 project uses the REST API to store and retrieve scan data.
The `plantimager.webui` package provides a web interface for interacting with the API, and the `plantimager.controller` package uses the API to store scan data.

For more information on how to use the API with Plant-Imager3, see the [developer documentation](developer/index.md).