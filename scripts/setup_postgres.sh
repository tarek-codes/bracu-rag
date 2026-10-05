#!/usr/bin/env bash
set -e

echo "=== Installing PostgreSQL 18 and pgvector ==="
sudo apt-get update
sudo apt-get install -y postgresql-18 postgresql-18-pgvector

echo "=== Starting PostgreSQL service ==="
sudo systemctl enable postgresql
sudo systemctl start postgresql

echo "=== Configuring PostgreSQL user and database ==="
# Set postgres password to 'postgres' (matching default dev .env) and create database bracu_rag
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'bracu_rag'" | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE bracu_rag OWNER postgres;"
sudo -u postgres psql -d bracu_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "=== Verification ==="
sudo -u postgres psql -d bracu_rag -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"

echo "=== Done! PostgreSQL 18 with pgvector is ready ==="
