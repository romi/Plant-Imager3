# Using the Services Stack

| Service     | Typical Use‑Case                                      | Endpoint Example                                         |
|-------------|-------------------------------------------------------|----------------------------------------------------------|
| **PlantDB** | Store plant image metadata, query experimental data.  | `http://plantimager.local:5000/plantdb/scan/dataset_123` |
| **P3DX**    | View a plant in 3D, interact with the scene.          | `http://plantimager.local/p3dx`                          |
| **P3DV**    | Run 3D reconstruction, view terminal sessions.        | `http://plantimager.local/p3dv`                          |
| **WebUI**   | Manage experiments, view real‑time imaging pipelines. | `http://plantimager.local:8080/webui`                    |

## Development Deployment

### Set up a local DNS

To route requests through a "fake" domain name for development purposes (in order to mimic the production setup), you can set up a local DNS on your machine (host) as follows:

1. Pick a "fake" domain (_e.g._ `plantimager.local`).
2. Add an entry to `/etc/hosts` that points that domain to `127.0.0.1`.
3. Tell Docker‑Compose to use the same host name by setting `SERVER_HOST` in the
   `.env` file (or via the environment section).
4. Make sure the `plantimager_nginx` image is built with that host name (`SERVER_HOST` is passed as a Docker build arg).

### Set up a local DNS server

If you want to avoid editing `/etc/hosts` and want a more scalable solution (
_e.g._ for multiple machines), you need to set up a DNS server.

1. Install and configure `dnsmasq`:
    ``` bash
    sudo apt-get install dnsmasq           # Debian/Ubuntu
    # or
    brew install dnsmasq                   # macOS
    ```

2. Create a configuration snippet:
    ``` text
    # /etc/dnsmasq.d/dev.local
    address=/dev.mellitus.local/127.0.0.1
    ```

3. Restart `dnsmasq`:
    ``` bash
    sudo systemctl restart dnsmasq
    ```

Now any machine on the same network that uses the local DNS server will resolve dev.mellitus.local to 127.0.0.1.

## Production Deployment

1. **Switch to the production network**  
   In `docker-compose.yml` set `plantimager-net` to `external: true` and create the network beforehand:

```shell script
docker network create plantimager-net
```

2. **Use a real SSL certificate** – Replace the `ssl_cert` volume with a persistent cert volume mounted to
   `/etc/nginx/ssl/`.

3. **Persist data** – Mount a real database volume for `plantdb` (`romi_db_test`) and for P3DV (`p3dv_cfg`,
   `webterm_users`).

4. **Disable development ports** – Remove or comment out the `ports:` entries for `plantdb`, `webui`, etc.

5. **Deploy** –

```shell script
docker compose -f docker-compose.yml up -d
```

The stack will now be reachable from the internet over HTTPS, with all services properly isolated on the
`plantimager-net`.

## Summary

* **NGINX** is the traffic controller that forwards requests based on URL prefixes.
* **PlantDB**, **P3DX**, **P3DV**, and **WebUI
  ** each run inside their own containers and expose their own WSGI/HTTP interfaces.
* **Docker volumes** keep data and certificates persistent, while the internal network (
  `plantimager-net`) allows name‑based service discovery.
* The `.env` file holds all host/port/prefix settings that keep the configuration consistent across all services.
