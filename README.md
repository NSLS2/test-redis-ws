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
- 3 Streaming API instances (fixed configuration)
- Traefik reverse proxy for load balancing

To start all services:
```sh
docker-compose up -d
# or with podman
podman-compose up -d
```

#### Accessing the Services

- **API**: http://localhost:8000/ (load balanced across all instances)
- **Traefik Dashboard**: http://localhost:8090 (see routing and load balancing info)
- **Redis**: localhost:6379 (if you need direct access)

#### Testing Load Balancing

To verify load balancing is working, run this command to see requests distributed across different server instances:
```sh
for i in {1..20}; do curl -s -D - http://localhost:8000/stream/live 2>/dev/null | grep X-Server-Host; done | sort
```

## NATS

Aka the better MQ, because it also has kv, and ... object store :D

### NATS server with jetstream

```shell
docker run -d --name nats-js -p 4222:4222 -p 8222:8222 nats:latest -js
```

### usage

Use the same writer and stream clients as with the Redis example.

Note: This is done quick and dirty and is a pure proof of concept!
It's failing hard and there are more uncovered edge cases than actually working cases.

Follow these steps:

1. start the NATS kv
2. start the "server" --> `pixi run -e nats serve-nats`
3. `pixi run write`
4. `pixi run stream`
