#!/bin/bash
# =============================================================================
# Trading Bot Full Stack Startup Script
# Inicia: PostgreSQL, Backend, API, Frontend
# =============================================================================

set -e

PROJECT_DIR="/home/user/trading-bot"
FRONTEND_PORT=3000
API_PORT=8000
DB_PORT=5432

echo "🚀 Trading Bot Full Stack Startup"
echo "=================================="

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar se .env existe
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo -e "${RED}❌ .env não encontrado!${NC}"
  echo "   Copie .env.example para .env e configure"
  exit 1
fi

# 2. Parar containers antigos (se estiverem rodando)
echo -e "\n${YELLOW}⏹️  Parando containers antigos...${NC}"
cd "$PROJECT_DIR"
docker-compose down 2>/dev/null || true
sleep 2

# 3. Iniciar Docker Compose stack
echo -e "\n${YELLOW}🐳 Iniciando Docker Compose (PostgreSQL + API + Bot)...${NC}"
docker-compose up -d

# 4. Aguardar services ficarem healthy
echo -e "\n${YELLOW}⏳ Aguardando services ficarem healthy (max 30s)...${NC}"
MAX_RETRIES=30
RETRIES=0
while [ $RETRIES -lt $MAX_RETRIES ]; do
  if docker-compose ps | grep -q "db.*healthy"; then
    echo -e "${GREEN}✅ PostgreSQL está pronto${NC}"
    break
  fi
  RETRIES=$((RETRIES + 1))
  sleep 1
done

sleep 3

# 5. Verificar status dos services
echo -e "\n${YELLOW}📊 Status dos Services:${NC}"
docker-compose ps

# 6. Iniciar Frontend em background
echo -e "\n${YELLOW}🌐 Iniciando Frontend em http://localhost:${FRONTEND_PORT}${NC}"
cd "$PROJECT_DIR"
python3 -m http.server $FRONTEND_PORT > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   PID: $FRONTEND_PID"

# 7. Aguardar um pouco para API ficar pronta
sleep 5

# 8. Testar endpoints
echo -e "\n${YELLOW}🧪 Testando Endpoints...${NC}"

# Frontend
if curl -s http://localhost:$FRONTEND_PORT/index.html > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Frontend rodando: http://localhost:$FRONTEND_PORT/index.html${NC}"
else
  echo -e "${RED}❌ Frontend não respondeu${NC}"
fi

# API
if curl -s http://localhost:$API_PORT/docs > /dev/null 2>&1; then
  echo -e "${GREEN}✅ API rodando: http://localhost:$API_PORT/docs${NC}"
else
  echo -e "${YELLOW}⏳ API ainda não está pronta, aguardando...${NC}"
  sleep 5
  if curl -s http://localhost:$API_PORT/docs > /dev/null 2>&1; then
    echo -e "${GREEN}✅ API rodando: http://localhost:$API_PORT/docs${NC}"
  else
    echo -e "${RED}⚠️  API pode estar demorando para iniciar. Verifique: docker-compose logs api${NC}"
  fi
fi

# 9. Exibir resumo final
echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}✅ STACK INICIADO COM SUCESSO!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "📱 ${YELLOW}FRONTEND:${NC}"
echo "   http://localhost:$FRONTEND_PORT/index.html"
echo ""
echo -e "🔌 ${YELLOW}API:${NC}"
echo "   http://localhost:$API_PORT"
echo "   Docs: http://localhost:$API_PORT/docs"
echo ""
echo -e "💾 ${YELLOW}DATABASE:${NC}"
echo "   postgres://trader:trader@localhost:$DB_PORT/trading"
echo ""
echo -e "🤖 ${YELLOW}BOT:${NC}"
echo "   Rodando em background (Docker)"
echo "   Status: docker-compose logs -f bot"
echo ""
echo -e "🛑 ${YELLOW}Para parar:${NC}"
echo "   1. docker-compose down (para backend)"
echo "   2. kill $FRONTEND_PID (para frontend)"
echo "   3. Ou execute: ./shutdown.sh"
echo ""
echo -e "${YELLOW}Modo DRY_RUN: $(grep 'DRY_RUN=' .env | cut -d= -f2)${NC}"
echo ""
