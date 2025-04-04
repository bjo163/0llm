#!/bin/bash
# File: dev-docker-build.sh
# Description: Rebuild and restart docker-compose dev environment with logs and commit changes to Git

set -e # Exit immediately if a command exits with a non-zero status

COMPOSE_FILE="docker-compose.dev.yml"

# Function to commit changes to Git with error handling
commit_changes() {
    if [ -z "$1" ]; then
        echo "❌ Commit message is required."
        exit 1
    fi
    git add . || { echo "❌ Failed to stage changes"; exit 1; }
    git commit -m "$1" || { echo "❌ Failed to commit changes"; exit 1; }
}

# Function to run Docker commands with error handling
run_docker_command() {
    "$@" || { echo "❌ Command failed: $*"; exit 1; }
}

# Function to check if a container is executable
check_container_exec() {
    local service_name=$1
    echo "🔍 Checking if $service_name can be executed..."
    
    # Attempt to exec into the container
    if docker exec "$service_name" sh -c "exit" 2>/dev/null; then
        echo "✅ $service_name is accessible!"
        return 0
    else
        echo "❌ $service_name is not accessible!"
        return 1
    fi
}

echo "📦 Stopping existing containers (if any)..."
run_docker_command docker compose -f "$COMPOSE_FILE" down

echo "🔧 Rebuilding and starting containers in detached mode..."
run_docker_command docker compose -f "$COMPOSE_FILE" up --build -d

echo "✅ Containers are starting..."

# Check each service to see if it can be accessed
for service in $(docker compose -f "$COMPOSE_FILE" config --services); do
    if check_container_exec "$service"; then
        echo "📄 Streaming logs for $service (Press Ctrl+C to stop):"
        run_docker_command docker compose -f "$COMPOSE_FILE" logs -f "$service"
    else
        echo "❌ Skipping logs for $service due to accessibility issue."
    fi
done

# Create a dynamic commit message with a Unix timestamp
commit_message="Commit on $(date +%s)"
commit_changes "$commit_message"

# Push to the main branch on the origin remote
run_docker_command git push origin main --force

# Push to the main branch on the space remote
run_docker_command git push space main --force
