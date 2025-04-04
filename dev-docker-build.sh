#dev-docker-build.sh
#!/bin/bash

# File: restart-dev.sh
# Description: Rebuild and restart docker-compose dev environment with logs

set -e  # Exit on error

COMPOSE_FILE="docker-compose.dev.yml"

echo "📦 Stopping existing containers (if any)..."
docker compose -f $COMPOSE_FILE down

echo "🔧 Rebuilding and starting containers in detached mode..."
docker compose -f $COMPOSE_FILE up --build -d

echo "✅ Containers are up and running:"
docker compose -f $COMPOSE_FILE ps

echo "📄 Streaming logs (Press Ctrl+C to stop):"
docker compose -f $COMPOSE_FILE logs -f
