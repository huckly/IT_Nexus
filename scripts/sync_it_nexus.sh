#!/bin/bash
# Syncs the IT_Nexus workspace to the public repository (Sanitized, Single Commit)

set -e

# Ensure we are in the root of the repo
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKSPACE_DIR="$REPO_ROOT/workspaces/IT_Nexus"

echo "Syncing workspaces/IT_Nexus to remote 'it_nexus' main branch (SINGLE COMMIT & SANITIZED)..."

# Create a temporary directory
TEMP_DIR=$(mktemp -d)

# Copy files. We use rsync to cleanly copy all contents.
rsync -a --exclude='.git' --exclude='venv' --exclude='__pycache__' "$WORKSPACE_DIR/" "$TEMP_DIR/"

echo "Running data sanitization..."
cd "$TEMP_DIR"
# Run the sanitization script
python3 scripts/sanitize_data.py

echo "Initializing temporary repository..."
git init --initial-branch=main
git add .
git commit -m "Update public sync (Sanitized)"

# Get original remote URL. 
# Since we are in the temp dir, we query the main repo's remote, or fallback to default.
cd "$REPO_ROOT"
ORIGINAL_REMOTE_URL=$(git config --get remote.it_nexus.url || echo "git@github.com:huckly/IT_Nexus.git")

# Go back to temp dir to push
cd "$TEMP_DIR"
git remote add it_nexus "$ORIGINAL_REMOTE_URL"

echo "Force pushing to public repository..."
git push it_nexus main --force

echo "Cleaning up..."
rm -rf "$TEMP_DIR"
echo "Sync completed successfully."
