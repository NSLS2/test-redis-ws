## Requirements

- Podman 4.0+ or Docker
- Podman-compose 1.0.6+ (for scaling support)
- Pixi (for local development)

## Quick Start

### Option 1: Manual Setup

```sh
docker run --net=host --rm -v ./redis:/usr/local/etc/redis --name test-redis redis redis-server /usr/local/etc/redis/redis.conf

pixi run serve
```

### Option 2: Docker Compose with Load Balancing

The project includes a Docker Compose configuration that sets up:
- Redis server
- Streaming API application (scalable to multiple instances)
- Traefik reverse proxy for load balancing

#### Running with Docker Compose

Start all services with a single API instance:
```sh
docker-compose up -d
# or with podman
podman-compose up -d
```

#### Running Multiple API Replicas

To run multiple instances of the Streaming API application with automatic load balancing:

```sh
# Run with 3 API instances
docker-compose up -d --scale streaming_api=3
# or with podman
podman-compose up -d --scale streaming_api=3
```

You can scale to any number of instances (e.g., `--scale streaming_api=5` for 5 instances).

**Note**: Scaling with `--scale` requires podman-compose 1.0.6+ or docker-compose.

#### Accessing the Services

- **API**: http://localhost:8000/ (load balanced across all instances)
- **Traefik Dashboard**: http://localhost:8090 (see routing and load balancing info)
- **Redis**: localhost:6379 (if you need direct access)

#### Testing Load Balancing

To verify load balancing is working, run this command to see requests distributed across different server instances:
```sh
for i in {1..20}; do curl -s -D - http://localhost:8000/stream/live 2>/dev/null | grep X-Server-Host; done
```

#### Stopping the Services

```sh
docker-compose down
# or with podman
podman-compose down
```
