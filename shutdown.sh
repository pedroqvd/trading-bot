#!/bin/bash
# =============================================================================
# Trading Bot Shutdown Script
# =============================================================================

set -e

PROJECT_DIR="/home/user/trading-bot"

echo "🛑 Parando Trading Bot Stack..."
echo "=================================="

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. Parar Docker Compose
echo -e "${YELLOW}Parando containers...${NC}"
cd "$PROJECT_DIR"
docker-compose down

# 2. Matar processos Python (frontend)
echo -e "${YELLOW}Parando Frontend...${NC}"
pkill -f "http.server 3000" || true

# 3. Aguardar um pouco
sleep 2

# 4. Confirmar
echo -e "${GREEN}✅ Stack parado com sucesso${NC}"
echo ""
echo "Para remover todos os dados (PostgreSQL):"
echo "  docker-compose down -v"
