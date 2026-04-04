# 🌾 AgriSubsidy — AI Oracle для Автоматизации Агросубсидий на Solana

> **Solana Hackathon 2024 submission** · AI-powered · On-chain proof · Real-time streaming

[![Solana](https://img.shields.io/badge/Solana-Devnet-9945FF?logo=solana)](https://explorer.solana.com/?cluster=devnet)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![Anchor](https://img.shields.io/badge/Anchor-0.29-FF7043)](https://anchor-lang.com)

---

## 🎯 Проблема

Государственные агросубсидии распределяются вручную, медленно и непрозрачно. Фермеры ждут месяцами. Коррупция и субъективность решений — системные проблемы.

## 💡 Решение

**AgriSubsidy** — децентрализованная система, где **GPT-4o анализирует спутниковые данные** (NDVI + погода) и **автоматически переводит субсидию фермеру** через Solana smart contract. Каждое решение — прозрачно на блокчейне.

---

## 🏗 Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    React Dashboard                          │
│   FarmerCards → Evaluate → AI Log Stream (SSE) → TX Link  │
└─────────────────────┬───────────────────────────────────────┘
                      │ fetch / SSE
┌─────────────────────▼───────────────────────────────────────┐
│              Python FastAPI Backend (AI Oracle)             │
│                                                             │
│  OpenWeatherMap API  →  Weather Data                       │
│  NDVI Satellite Mock →  Vegetation Index                   │
│  Scoring Engine      →  Composite Score (0–100)            │
│  GPT-4o Agent        →  Chain-of-Thought Reasoning         │
│  Fallback Agent      →  Works without OpenAI               │
└─────────────────────┬───────────────────────────────────────┘
                      │ solders (Python Solana SDK)
┌─────────────────────▼───────────────────────────────────────┐
│           Anchor Smart Contract (Solana Devnet)             │
│                                                             │
│  initialize_subsidy_pool  →  Creates PDA escrow            │
│  register_farmer          →  On-chain farmer record        │
│  release_funds_by_oracle  →  Oracle signs → SOL transfer   │
│  reject_farmer            →  On-chain rejection record     │
└─────────────────────────────────────────────────────────────┘
```

## 🔐 Dual-Key Security Architecture

```
ADMIN_KEY  →  Initializes pool, manages farmers
ORACLE_KEY →  ONLY key that can call release_funds_by_oracle
               ↓ Lives in Python backend ONLY, never on frontend
```

---

## 📁 Структура проекта

```
agri-subsidy/
├── agent/                    # Python AI Backend
│   ├── main.py               # FastAPI server + SSE endpoints
│   ├── ai_agent.py           # GPT-4o chain-of-thought
│   ├── fallback_agent.py     # Offline fallback (5 scenarios)
│   ├── scoring_engine.py     # Composite scoring algorithm
│   ├── weather_service.py    # OpenWeatherMap real API
│   ├── ndvi_service.py       # Mock NDVI satellite data
│   ├── solana_bridge.py      # Python → Solana TX builder
│   ├── generate_keypair.py   # One-time keypair setup
│   ├── models.py             # Pydantic schemas
│   └── config.py             # Env loader
│
├── contracts/                # Anchor Smart Contract
│   ├── Anchor.toml
│   ├── Cargo.toml
│   ├── programs/agri_subsidy/
│   │   ├── src/lib.rs        # Contract: 4 instructions + events
│   │   └── Cargo.toml
│   └── tests/
│       └── agri_subsidy.test.ts
│
└── dashboard/                # React + Vite Frontend
    └── src/
        ├── App.jsx
        ├── components/
        │   ├── Header.jsx
        │   ├── FarmerCard.jsx      # Region, status, score gauge
        │   ├── AILogStream.jsx     # Real-time SSE log viewer
        │   ├── ScoreGauge.jsx      # Animated circular gauge
        │   ├── TxConfirmation.jsx  # Solana Explorer link
        │   └── StatsPanel.jsx      # Aggregate stats
        └── hooks/
            └── useSSE.js           # SSE streaming hook
```

---

## 🚀 Быстрый старт

### 1. Клонирование и настройка

```bash
git clone <repo>
cd agri-subsidy/agent
```

### 2. Python Backend

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка .env
cp .env.example .env
# Заполни OPENAI_API_KEY и OPENWEATHER_API_KEY

# Генерация Oracle keypair (один раз)
python generate_keypair.py

# Запрос Devnet SOL для Oracle
# Скопируй ORACLE_PUBKEY из .env и вставь на https://faucet.solana.com

# Запуск сервера
python -m uvicorn main:app --reload --port 8000
```

### 3. React Dashboard

```bash
cd ../dashboard
npm install
npm run dev
# Открыть http://localhost:5173
```

### 4. Anchor Smart Contract (требует WSL2 на Windows)

```bash
# В WSL2:
cd contracts/

# Установка Rust + Solana + Anchor (если нет)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
sh -c "$(curl -sSfL https://release.solana.com/v1.18.0/install)"
cargo install --git https://github.com/coral-xyz/anchor anchor-cli --locked

# Настройка Devnet
solana config set --url devnet
solana-keygen new --outfile ~/.config/solana/id.json
solana airdrop 4

# Деплой
anchor build
anchor deploy

# Тесты
anchor test
```

### 5. После деплоя контракта

```bash
# Скопируй program ID из вывода `anchor deploy`
# Вставь в agent/.env:
echo "PROGRAM_ID=<your_program_id>" >> agent/.env

# Перезапусти бэкенд — bridge автоматически переключится в LIVE режим
```

---

## 🎬 Demo Flow

1. **Открой** → http://localhost:5173
2. **Load Demo** → загружает 5 фермеров из разных регионов
3. **Evaluate** → нажми для любого фермера
4. **Watch AI think** → GPT-4o анализирует данные в реальном времени
5. **See verdict** → Score gauge анимируется, решение появляется
6. **Click Explorer** → переходи на Solana Explorer и видишь TX

---

## 🏜️ Demo Mode — Aktobe Region Stress Case

> **For hackathon judges:** One of the five demo farmers (Aktobe Region, `FZA62o7r...`) is pre-configured with a synthetic extreme drought scenario. This is an intentional design choice, not a bug.
>
> **Why we did this:** The Aktobe region in Western Kazakhstan has a semi-arid continental climate prone to severe droughts. To reliably demonstrate the full end-to-end flow — including a successful on-chain subsidy transfer — during a live demo, we hard-code the following conditions for this farmer in `agent/main.py`:
>
> | Parameter | Demo Value | Real-World Equivalent |
> |---|---|---|
> | Temperature | +45.0°C | Extreme summer heat wave |
> | Humidity | 5% | Critical drought conditions |
> | Rainfall | 0.0 mm/h | Total precipitation deficit |
> | NDVI | 0.15 | ~74% crop loss vs historical avg |
>
> This yields a **composite AI score of ~95/100**, passes the smart contract's hardcoded threshold (`ai_score >= 55`), and results in a live SOL transfer on Solana Devnet. All other four farmers receive **real, live weather data** from OpenWeatherMap API.

---


| Фермер | Регион | Условия | Ожидаемый результат |
|--------|--------|---------|-------------------|
| DemoFarm1 | Костанайская область | Зерновой пояс, степной климат | Зависит от сезона |
| DemoFarm2 | Северо-Казахстанская область | Северный зерновой регион | Зависит от осадков |
| DemoFarm3 | Акмолинская область | Умеренно-континентальный | ❌ Обычно отклонено |
| DemoFarm4 | Актюбинская область | Более засушливый западный регион | ✅ Наглядный stress-case |
| DemoFarm5 | Алматинская область | Южный аграрный регион | Зависит от NDVI |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/demo/seed` | Load 5 demo farmers |
| `GET`  | `/api/farmers` | List all farmers with status |
| `POST` | `/api/farmers/register` | Register new farmer |
| `POST` | `/api/evaluate` | Start AI evaluation → returns `evaluation_id` |
| `GET`  | `/api/stream/{id}` | **SSE stream** of AI reasoning |
| `GET`  | `/api/stats` | Aggregate statistics |
| `GET`  | `/api/tx/{sig}` | Check Solana TX status |
| `GET`  | `/health` | Health check |
| `GET`  | `/docs` | Swagger UI |

---

## 🧠 Scoring Algorithm

```python
composite_score = weather_score * 0.4 + ndvi_score * 0.4 + history_score * 0.2

# Approval threshold: 55/100

# Weather factors:
#   Temperature > 38°C    → +50 (extreme heat)
#   Humidity < 20%        → +35 (drought risk)
#   No rain (0 mm/h)      → +15

# NDVI factors:
#   NDVI < 0.2            → +95 (critical vegetation loss)
#   NDVI < 0.35           → +80
#   NDVI < 0.5            → +60
#   NDVI > 0.65           → +15 (healthy crops)
```

---

## ⛓ Smart Contract Instructions

```rust
// 1. Admin initializes the pool with oracle key
initialize_subsidy_pool(pool_bump: u8)

// 2. Admin registers farmer on-chain
register_farmer(region_code: String)

// 3. Oracle releases funds (score must be >= 55)
release_funds_by_oracle(amount: u64, ai_score: u8)

// 4. Oracle marks farmer rejected (no funds, on-chain record)
reject_farmer(ai_score: u8)
```

---

## 🛡 Security

- **Oracle key** never leaves the backend (env variable, never in frontend)
- **Smart contract** enforces oracle authorization on-chain
- **Score threshold** hardcoded in contract — AI can't bypass it
- **Amount cap** — max 5 SOL per farmer per transaction
- **PDA escrow** — funds locked in program-controlled account

---

## 🏆 Hackathon Highlights

- ✅ **Live AI reasoning** streamed token-by-token via SSE
- ✅ **Real OpenWeatherMap data** for farmer locations
- ✅ **On-chain proof** — every decision recorded on Solana
- ✅ **Fallback mode** — works even if OpenAI is down (demo never fails)
- ✅ **Solana Explorer** links for every approved transaction
- ✅ **Dual-key security** — oracle key separation
- ✅ **Mobile-responsive** dashboard

---

## 👥 Team

Built for Solana Hackathon · Powered by GPT-4o + Anchor + React

---

*"Transparency in every grain of wheat"* 🌾
