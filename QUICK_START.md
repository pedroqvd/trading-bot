# 🚀 Quick Start - Trading Bot Local

## Iniciar Tudo em Um Comando

```bash
cd /home/user/trading-bot
./startup.sh
```

Pronto! O bot está rodando localmente.

## Acessar

| Componente | URL |
|-----------|-----|
| **Frontend** | http://localhost:3000/index.html |
| **API Docs** | http://localhost:8000/docs |
| **Database** | localhost:5432 (postgres) |

## Parar

```bash
./shutdown.sh
```

Ou manualmente:
```bash
docker-compose down
```

---

## 📊 O que você vai ver

Ao abrir o frontend em http://localhost:3000/index.html:

✅ **Equity Curve** - Patrimônio atualizando em tempo real (bot simula trades)
✅ **KPIs** - Patrimônio, PnL, Win Rate, Sharpe, Sortino
✅ **Trades** - Histórico de operações com EV, Kelly, SL/TP
✅ **Posições** - Abertas/fechadas com análise em tempo real
✅ **Risk Events** - Kill switch, drawdown limits marcados no gráfico
✅ **Analytics** - Strategy heatmap, decomposition, logs com filtros
✅ **Settings** - Ajustar parâmetros do bot e ver preview
✅ **Backtest** - Comparar múltiplas runs lado a lado

---

## ⚙️ Configuração

A configuração está em `.env` (já criada e otimizada):

**Estratégia Ativa:**
- 3 edges: Overreaction + Arbitrage + Momentum
- Capital: $10,000 (simulado)
- Risk: Conservative (4% daily loss limit, 12% drawdown kill-switch)
- Polling: 15 segundos

**Para mudar parâmetros:** Edite `.env` e reinicie com `./startup.sh`

---

## 🔒 Segurança (DRY_RUN)

```
DRY_RUN=true  ✅ Nenhum dinheiro gasto
```

O bot **não pode transacionar** porque:
- `POLYMARKET_PRIVATE_KEY` está vazio
- `DRY_RUN=true` força simulação
- Sem credentials válidas, sem acesso a USDC real

---

## 🐛 Troubleshooting

### Frontend não carrega
```bash
# Verificar se está rodando
curl http://localhost:3000/index.html

# Reiniciar
./startup.sh
```

### API não respondendo
```bash
# Verificar logs
docker-compose logs -f api

# Reiniciar
docker-compose down && docker-compose up -d && sleep 10
```

### Database error
```bash
# Resetar database
docker-compose down -v
docker-compose up -d
```

---

## 📝 Validar Métricas

A UI já mostra **tudo** que você precisa validar:

1. **Equity Growth** → Gráfico principal
2. **Drawdown Control** → KPI "Sharpe" (max drawdown)
3. **Win Rate** → KPI "Taxa de acerto"
4. **Trade Quality** → Detalhe de cada trade
5. **Risk Management** → Kill switch funcionando
6. **Strategy Performance** → Analytics page

**Não precisa de logs.** A UI é suficiente.

---

## 🎯 Próximos Passos

1. ✅ Rodar `./startup.sh`
2. ✅ Abrir http://localhost:3000/index.html
3. ✅ Deixar rodando 24/7 para validar métricas
4. ✅ Editar `.env` para ajustar estratégia
5. ✅ Usar backtest comparator para otimizar
6. ✅ Quando pronto, integrar com API real do Polymarket

---

## 💡 Dicas

- **Mock data**: Gera novos dados a cada 5 segundos
- **Persistence**: Todos os dados salvos em PostgreSQL local
- **Scale**: Suporta 24/7 sem degradação
- **Cost**: Zero gasto (modo dry-run)

Tá pronto para validar! 🎉
