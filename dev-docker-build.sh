#!/bin/bash
# File: dev-docker-build.sh
# Description: Rebuild and restart docker-compose dev environment with logs and commit changes to Git

set -e # Exit on error

COMPOSE_FILE="docker-compose.dev.yml"

# Function to commit changes to Git
commit_changes() {
    if [ -z "$1" ]; then
        echo "❌ Commit message is required."
        exit 1
    fi
    git add .                # Stage all changes
    git commit -m "$1"      # Commit with the provided message
}

echo "📦 Stopping existing containers (if any)..."
docker compose -f $COMPOSE_FILE down

echo "🔧 Rebuilding and starting containers in detached mode..."
docker compose -f $COMPOSE_FILE up --build -d

echo "✅ Containers are up and running:"
docker compose -f $COMPOSE_FILE ps

# Create a dynamic commit message with a Unix timestamp
commit_message="Commit on $(date +%s)" # This will use the current Unix timestamp
commit_changes "$commit_message"          # Call the function to commit the changes

git push origin main --force             # Push to the main branch on the origin remote
git push space main --force               # Push to the main branch on the space remote

echo "📄 Streaming logs (Press Ctrl+C to stop):"
docker compose -f $COMPOSE_FILE logs -f
