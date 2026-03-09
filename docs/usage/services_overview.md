# Plant‑Imager Service Architecture Overview

![isoflow-v3_full_stack_architecture.png](../assets/images/isoflow-v3_full_stack_architecture.png)

The Plant‑Imager service stack is split into several Docker containers that work together to provide a complete
workflow:

| Service      | Purpose                                                                                          | Key Env Vars                                                                                                                                                                                                 | Communication                                                                                   |
|--------------|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| **ssl_cert** | Copies SSL certificates into a shared volume (`nginx_cert`).                                     | `SERVER_HOST`, `CONTROLLER_HOST`, etc. (used by `nginx`)                                                                                                                                                     | Provides certificates to NGINX via a shared Docker volume.                                      |
| **nginx**    | Reverse proxy that exposes public ports (80/443) and forwards requests to the internal services. | `SERVER_HOST`, `CONTROLLER_HOST`, `CONTROLLER_PORT`, `CONTROLLER_PREFIX`, `PLANTDB_HOST`, `PLANTDB_PORT`, `PLANTDB_PREFIX`, `P3DX_HOST`, `P3DX_PORT`, `P3DX_PREFIX`, `P3DV_HOST`, `P3DV_PORT`, `P3DV_PREFIX` | Routes traffic from the host to the appropriate internal container using the `plantimager-net`. |
| **plantdb**  | REST API for the Plant Database (data storage, queries, etc.).                                   | `PLANTDB_API_PREFIX`, `PLANTDB_API_SSL`                                                                                                                                                                      | Exposed via uWSGI on `${PLANTDB_PORT}`; NGINX proxies `/plantdb` requests to this container.    |
| **webui**    | WebUI controller for plant scanning.                                                             | `ALLOW_PRIVATE_IP`, `CERT_PATH`, `PLANTDB_HOST`, `PLANTDB_PREFIX`, `WEBUI_PROXY`, `WEBUI_PREFIX`                                                                                                             | Exposes itself on `${CONTROLLER_PORT}`; NGINX proxies `/webui`.                                 |
| **p3dv**     | Plant 3D Vision – WebTerm for data processing (reconstruction and quantifications).              | `PLANTDB_API`, `WEBTERM_PROXY`, `WEBTERM_PREFIX`                                                                                                                                                             | Runs Gunicorn/WSGI on `${P3DV_PORT}`; NGINX proxies `/p3dv`.                                    |
| **p3dx**     | Plant 3D Explorer – JS/REACT interactive 3D viewer.                                              | `API_URL`, `BASENAME`                                                                                                                                                                                        | Exposes a static web app on `${P3DX_PORT}`; NGINX proxies `/p3dx`.                              |

> **Note**  
> The `ssl_cert` container is only needed if you use a self‑signed certificate.
> In production you may want to use Let's Encrypt certificates using a certbot and point
`nginx` at a persistent cert volume and disable this service.


## How the Components Talk to Each Other

1. **Docker Network (`plantimager-net`)** – All services are attached to the same internal Docker bridge.  
   *Containers resolve each other by name (`plantdb`, `p3dx`, `p3dv`, `webui`).*

2. **NGINX Reverse Proxy** – Acts as the single entry point for external clients.  
   *Ports `80` and `443` are mapped to the host.  
   *Based on URL prefixes (`/webui`, `/plantdb`, `/p3dx`, `/p3dv`) NGINX forwards traffic to the respective containers.*

3. **uWSGI / Gunicorn** – Both `plantdb` and `webui` expose a WSGI application.  
   *uWSGI (in `plantdb`and `webui`) and Gunicorn (in `p3dv`) listen on the container’s internal port and are reached by
   NGINX.*

4. **Health‑check URLs** – Each container runs a simple `curl` check (
   `/health` or the root URL) to confirm the service are ready
