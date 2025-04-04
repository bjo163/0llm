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
    "$@" || { echo "❌ Docker command failed: $*"; exit 1; }
}

echo "📦 Stopping existing containers (if any)..."
run_docker_command docker compose -f "$COMPOSE_FILE" down

echo "🔧 Rebuilding and starting containers in detached mode..."
run_docker_command docker compose -f "$COMPOSE_FILE" up --build -d

echo "✅ Containers are up and running:"
run_docker_command docker compose -f "$COMPOSE_FILE" ps

# Create a dynamic commit message with a Unix timestamp
commit_message="Commit on $(date +%s)" # This will use the current Unix timestamp
commit_changes "$commit_message" # Call the function to commit the changes

# Push to the main branch on the origin remote
run_docker_command git push origin main --force
# Push to the main branch on the space remote
run_docker_command git push space main --force

echo "📄 Streaming logs (Press Ctrl+C to stop):"
run_docker_command docker compose -f "$COMPOSE_FILE" logs -f
