# Kizuna

A production-grade, five-department AI chat platform combining **Gemini 2.5 Flash**, **Google ADK agents**, **Composio v3 tool integrations**, and **department-based access control**. Each department gets a dedicated ADK agent with role-specific prompts and a scoped set of Composio-managed SaaS tools.

---

## Architecture Overview

```mermaid
graph TB
    subgraph Frontend["Frontend (Next.js)"]
        UI[Chat UI]
        Auth[Auth Context]
        API[API Client]
        CB[OAuth Callback]
    end

    subgraph Backend["Backend (FastAPI)"]
        GW[API Gateway<br/>CORS + Rate Limiter +<br/>Security Headers + CSP/HSTS]

        subgraph Routers
            AR[Auth Router<br/>/api/auth]
            CR[Chat Router<br/>/api/chat]
            SR[Sessions Router<br/>/api/sessions]
            UR[Upload Router<br/>/api/upload]
            CN[Connectors Router<br/>/api/connectors]
        end

        subgraph Agents["ADK Agents (per-department)"]
            AA[Admin Agent]
            SA[Sales Agent]
            OA[Operations Agent]
            FA[Finance Agent]
            EA[Executive Agent]
            AR2[Agent Router<br/>department → factory]
            RN[Agent Runner<br/>ADK event loop]
        end

        subgraph Services
            AS[Auth Service<br/>JWT + PBKDF2 + Blacklist]
            PE[Prompt Engine<br/>5 Department Prompts]
            SMS[Summary Service<br/>Rolling session summary]
            SS[Session Store<br/>CRUD + Documents]
        end

        subgraph Middleware
            RBAC[RBAC Middleware<br/>Cookie + Bearer JWT<br/>+ Blacklist Check +<br/>Department Checks]
        end
    end

    subgraph External["External Services"]
        GEM[Gemini API<br/>2.5 Flash]
        COM[Composio v3<br/>Managed OAuth + Tools]
    end

    subgraph Storage["Database"]
        DB[(SQLite / PostgreSQL)]
    end

    UI --> API
    Auth --> API
    API --> GW
    CB -->|postMessage| UI

    GW --> AR
    GW --> CR
    GW --> SR
    GW --> UR
    GW --> CN

    AR --> AS
    CR --> AR2
    AR2 --> AA
    AR2 --> SA
    AR2 --> OA
    AR2 --> FA
    AR2 --> EA
    CR --> RN
    CR --> SS
    CR --> SMS
    SR --> SS
    CN -->|Auth + Status| COM

    AA -->|tools| COM
    SA -->|tools| COM
    OA -->|tools| COM
    FA -->|tools| COM
    EA -->|tools| COM

    RN --> GEM
    AA --> PE
    SA --> PE
    OA --> PE
    FA --> PE
    EA --> PE

    AS --> DB
    SS --> DB
    SMS --> DB
    RBAC --> AS
```

---

## Request Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant GW as API Gateway
    participant RBAC as RBAC Middleware
    participant Chat as Chat Router
    participant Router as Agent Router
    participant Agent as ADK Agent
    participant Gemini as Gemini 2.5
    participant Com as Composio
    participant DB as Database

    U->>FE: Type message + send
    FE->>GW: POST /api/chat/stream (cookie JWT)
    GW->>RBAC: Validate cookie / bearer
    RBAC->>DB: Check blacklist + verify active user
    RBAC-->>Chat: user {id, department, jti}

    Chat->>DB: Get/create session
    Chat->>DB: Store user message
    Chat->>DB: Load history + session summary

    Chat->>Router: get_agent_for_department(dept, user_id)
    Router->>Com: Load scoped tools (cached 5m)
    Com-->>Router: ADK-native tools
    Router-->>Chat: Fresh Agent instance

    Chat->>Agent: run_agent_streaming(message, summary)
    loop Until final response
        Agent->>Gemini: Generate turn
        Gemini-->>Agent: text or function_call
        alt Function call
            Agent->>Com: Execute tool
            Com-->>Agent: Tool result
            Chat-->>FE: SSE tool_start / tool_end
        end
    end
    Agent-->>Chat: Structured final response

    Chat->>DB: Store assistant message
    Chat->>DB: Update rolling session summary
    Chat-->>FE: SSE structured event
    FE-->>U: Animated response with tool traces
```

---

## Connector Flow (Composio v3)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend (Popup)
    participant BE as Backend
    participant Com as Composio

    U->>FE: Click "Connect" on toolkit
    FE->>BE: POST /api/connectors/{toolkit}/auth
    BE->>BE: Verify toolkit allowed for department
    BE->>Com: composio.create(user_id).authorize(toolkit)
    Com-->>BE: {redirect_url, connection_id}
    BE-->>FE: {auth_url, connection_id}

    FE->>FE: Open popup
    FE->>Com: Redirect to auth_url
    U->>Com: Approve OAuth with provider
    Com-->>FE: Popup closes / redirect

    FE->>BE: GET /api/connectors/{toolkit}/status
    BE->>Com: composio.connected_accounts.list(user)
    Com-->>BE: {status: ACTIVE}
    BE-->>FE: {status: ACTIVE}
    FE->>FE: Refresh connector list
```

Composio manages all OAuth provider registrations, token storage, and refresh — the backend only ever sees `user_id`, toolkit slug, and connection status.

---

## Database Schema

```mermaid
erDiagram
    users {
        string id PK "UUID"
        string email UK "indexed, EmailStr"
        string password_hash "PBKDF2-SHA256 600k"
        string name
        string department "admin|sales|operations|finance|executive"
        int is_active "soft delete"
        datetime created_at
        datetime updated_at
    }

    chat_sessions {
        string id PK "UUID"
        string title "auto-generated"
        string department "indexed"
        string user_id FK
        text document_context "nullable"
        string document_name
        text session_summary "rolling context"
        int summary_msg_count
        datetime created_at
        datetime updated_at
    }

    chat_messages {
        int id PK "auto-increment"
        string session_id FK "indexed"
        string role "user|assistant"
        text content
        datetime created_at
    }

    token_blacklist {
        int id PK "auto-increment"
        string jti UK "JWT ID, indexed"
        string user_id FK
        datetime revoked_at
        datetime expires_at "indexed for cleanup"
    }

    users ||--o{ chat_sessions : "has"
    users ||--o{ token_blacklist : "revokes"
    chat_sessions ||--o{ chat_messages : "contains"
```

Composio handles all connected-account state — there is no local `user_connectors` table; connection status is fetched live via `composio.connected_accounts.list()`.

---

## Department System

```mermaid
graph LR
    subgraph Departments
        ADM[Admin<br/>Blue #7c9dff]
        SAL[Sales<br/>Teal #6dcba1]
        OPS[Operations<br/>Orange #d4a574]
        FIN[Finance<br/>Cyan #6bc5d9]
        EXE[Executive<br/>Purple #d4829a]
    end

    subgraph Personas
        P1[Strategic Leadership<br/>Advisor]
        P2[Revenue Growth<br/>Advisor]
        P3[Process Optimization<br/>Specialist]
        P4[Financial Analysis<br/>Specialist]
        P5[C-Suite Intelligence<br/>Advisor]
    end

    subgraph Toolkits
        T1[Google Workspace<br/>Gmail, Chat, Calendar,<br/>Meet, Drive, Sheets,<br/>Docs, Slides]
        T2[Google Workspace +<br/>HubSpot CRM]
        T3[Google Workspace +<br/>Jira]
        T4[Google Workspace]
        T5[Google Workspace +<br/>HubSpot + Jira]
    end

    ADM --> P1 --> T1
    SAL --> P2 --> T2
    OPS --> P3 --> T3
    FIN --> P4 --> T4
    EXE --> P5 --> T5
```

Each department has **5 prompt templates** (25 total) for common tasks like forecasting, report generation, compliance checklists, etc. Agent factories in `backend/agents/` build a fresh ADK `Agent` per request, scoped to the user's department toolkits.

---

## Session Context System

```mermaid
graph LR
    subgraph Input
        HIST[Conversation<br/>History]
        NEW[New Message]
    end

    subgraph Context["Rolling Summary (per session)"]
        SUM[Session Summary<br/>Stored in DB]
        TH[Threshold Check<br/>N messages since<br/>last summary]
        REG[Regenerate<br/>via Gemini]
    end

    subgraph Injection
        PROMPT[Agent Prompt<br/>System + Summary +<br/>Full history]
    end

    HIST --> PROMPT
    NEW --> PROMPT
    SUM --> PROMPT

    NEW --> TH
    TH -->|threshold hit| REG
    REG --> SUM
```

Instead of a vector memory store, Triton uses a **rolling session summary** regenerated periodically by Gemini and stored alongside the session in the database. This keeps long conversations coherent without the cost and latency of embedding + vector search on every turn.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js, React 19, TypeScript, Tailwind CSS |
| **Backend** | FastAPI, Uvicorn, SQLAlchemy |
| **LLM** | Gemini 2.0 Flash (OpenRouter) |
| **Agents** | OpenAI SDK (OpenRouter-compatible) |
| **Connectors** | Composio v3 SDK |
| **Database** | SQLite (dev) / PostgreSQL (prod) |
| **Auth** | JWT in httpOnly cookie + PBKDF2-SHA256 (600k) + token blacklist |
| **Rate Limiting** | slowapi (login 10/min, register 5/hr, chat 30/min) |
| **Containerization** | Docker + Docker Compose |

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- [Gemini API Key](https://aistudio.google.com) (required)
- [Composio API Key](https://composio.dev) (required for tools)
- (Optional) Docker & Docker Compose

### 1. Clone the Repository

```bash
git clone https://github.com/TetraNoodle-Technologies/Triton---AI-matchone-medical.git
cd Triton---AI-matchone-medical
```

### 2. Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example backend/.env
```

Edit `backend/.env` and set the required values:

```env
# Required
OPENROUTER_API_KEY=your_openrouter_api_key
COMPOSIO_API_KEY=your_composio_api_key
JWT_SECRET=$(openssl rand -hex 32)

# Optional overrides
LLM_MODEL=google/gemini-3.5-flash
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
RATE_LIMIT_PER_MINUTE=30
```

### 4. Frontend Setup

```bash
cd frontend
npm install
```

### 5. Run the Application

**Development (two terminals):**

```bash
# Terminal 1 — Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

**Docker Compose (production-style):**

```bash
export POSTGRES_PASSWORD=your_db_password
export OPENROUTER_API_KEY=your_openrouter_key
export COMPOSIO_API_KEY=your_composio_key
export JWT_SECRET=$(openssl rand -hex 32)

docker compose up --build
```

### 6. Access the Application

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/api/docs *(dev only)* |
| API Docs (ReDoc) | http://localhost:8000/api/redoc *(dev only)* |
| Health Check | http://localhost:8000/api/health |

API docs are disabled when `ENVIRONMENT=production`.

---

## Deployment Diagram

```mermaid
graph TB
    subgraph Docker["Docker Compose"]
        subgraph FE["frontend :3000"]
            NEXT[Next.js<br/>node:20-alpine<br/>user: nextjs]
        end

        subgraph BE["backend :8000"]
            FAST[FastAPI + Uvicorn<br/>python:3.12-slim<br/>user: appuser<br/>2 workers]
        end

        subgraph PG["db :5432"]
            POSTGRES[PostgreSQL 16<br/>Alpine]
        end

        VOLUMES[(Volumes<br/>postgres_data<br/>upload_data)]
    end

    FE -->|API calls + cookie| BE
    BE -->|SQLAlchemy| PG
    BE -->|Uploads| VOLUMES
    PG -->|Data| VOLUMES

    BE -->|HTTPS| GEM[Gemini API]
    BE -->|HTTPS| COM[Composio]
```

---

## API Endpoints

### Authentication

| Method | Endpoint | Description | Auth | Rate Limit |
|--------|----------|-------------|------|------------|
| POST | `/api/auth/register` | Register new user | None | 5/hour |
| POST | `/api/auth/login` | Login, sets httpOnly cookie + returns JWT | None | 10/minute |
| POST | `/api/auth/logout` | Revoke current token (blacklist jti) | Cookie/Bearer | — |
| GET | `/api/auth/me` | Get current user | Cookie/Bearer | — |
| GET | `/api/auth/users` | List users (admin only) | Cookie/Bearer | — |
| DELETE | `/api/auth/users/{id}` | Deactivate user (admin) | Cookie/Bearer | — |

### Chat

| Method | Endpoint | Description | Auth | Rate Limit |
|--------|----------|-------------|------|------------|
| POST | `/api/chat` | Send message, get structured response | Cookie/Bearer | 30/minute |
| POST | `/api/chat/stream` | Send message, SSE stream with tool traces | Cookie/Bearer | 30/minute |

### Sessions

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/sessions` | Create new session | Cookie/Bearer |
| GET | `/api/sessions` | List user's sessions | Cookie/Bearer |
| GET | `/api/sessions/{id}` | Get session with messages | Cookie/Bearer |
| DELETE | `/api/sessions/{id}` | Delete session | Cookie/Bearer |
| GET | `/api/sessions/templates/prompts` | Get department templates | Cookie/Bearer |

### Connectors (Composio-backed)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/connectors` | List toolkits for user's department with status | Cookie/Bearer |
| POST | `/api/connectors/{toolkit}/auth` | Start Composio OAuth, returns redirect URL | Cookie/Bearer |
| GET | `/api/connectors/{toolkit}/status` | Check connection status | Cookie/Bearer |
| POST | `/api/connectors/{toolkit}/disconnect` | Remove connection | Cookie/Bearer |

### Upload

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/upload` | Upload document (max 10MB) | Cookie/Bearer |

Supported formats: `.pdf`, `.docx`, `.csv`, `.xlsx`, `.txt`, `.md`

### Health

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/health` | Basic health check | None |
| GET | `/api/health/deep` | DB connectivity | None |

---

## Structured Response Format

All chat responses follow a consistent JSON schema:

```json
{
  "title": "Quarterly Revenue Summary",
  "summary": "Revenue grew 12% QoQ driven by enterprise expansion.",
  "sections": [
    {
      "heading": "Revenue Breakdown",
      "content": "**Enterprise**: $2.4M (+18%)\n\n**SMB**: $1.1M (+5%)\n\n| Metric | Q3 | Q4 |\n|--------|-----|-----|\n| MRR | $290K | $325K |"
    },
    {
      "heading": "Key Drivers",
      "content": "- Enterprise deal pipeline increased by 23%\n- Churn rate decreased to 1.8%"
    }
  ],
  "key_takeaways": [
    "Enterprise segment is the primary growth driver",
    "Churn reduction contributed $140K in retained revenue",
    "Pipeline suggests continued acceleration in Q1"
  ],
  "tool_calls": [
    { "name": "Gmail: Send Email", "raw_name": "GMAIL_SEND_EMAIL", "status": "success" }
  ]
}
```

The streaming endpoint additionally emits `tool_start` / `tool_end` SSE events as the agent invokes each tool, so the UI can render live tool traces.

---

## Available Connectors

```mermaid
graph TB
    subgraph GoogleWorkspace["Google Workspace"]
        GM[Gmail]
        GCH[Google Chat]
        GC[Google Calendar]
        GMT[Google Meet]
        GD[Google Drive]
        GS[Google Sheets]
        GDC[Google Docs]
        GSL[Google Slides]
    end

    subgraph CRM
        HS[HubSpot]
    end

    subgraph ProjectMgmt["Project Management"]
        JI[Jira]
    end

    POLARIS((Triton)) --> GoogleWorkspace
    POLARIS --> CRM
    POLARIS --> ProjectMgmt
```

All connectors are managed by [Composio](https://composio.dev) — OAuth registration, token storage, and refresh are handled by Composio's managed auth; the backend only sees connection status via `composio.connected_accounts.list()`.

---

## Security

| Feature | Implementation |
|---------|---------------|
| Password Hashing | PBKDF2-SHA256, 600k iterations, 32-byte random salt |
| Authentication | JWT in httpOnly cookie (7-day expiry) + optional `Authorization: Bearer` for API clients |
| Token Revocation | `token_blacklist` table; logout inserts `jti`, every request checks |
| Email / Input Validation | Pydantic `EmailStr`, length-bounded fields, stripped names |
| CORS | Restricted origins, `PUT`/`OPTIONS` dropped, wildcard rejected in production |
| Rate Limiting | 30/min chat, 10/min login, 5/hour register |
| Security Headers | CSP, HSTS *(prod)*, X-Frame-Options, Referrer-Policy, Permissions-Policy |
| Cache Control | `no-store` on authenticated `/api/*` responses |
| File Upload | Extension + MIME validation, sanitized filenames, path traversal protection |
| XSS Prevention | rehype-sanitize for markdown, HTML-escaped OAuth callbacks |
| Docker | Non-root containers (appuser / nextjs) |
| Input Length | Max 10k chars per message, 50k chars per document |
| DB Migrations | Allow-listed column adds to prevent SQL injection via `ALTER TABLE` |
| Environment Guards | Production mode blocks SQLite, wildcard CORS, and hides API docs |
| Error Handling | Incident IDs in logs; clients receive only `"Internal server error"` |

---

## Project Structure

```
polaris/
├── backend/
│   ├── main.py                    # FastAPI app, CORS, rate limiter, security headers, CSP
│   ├── config.py                  # Settings, env validation, prod guards
│   ├── models.py                  # Pydantic request/response models
│   ├── Dockerfile                 # Python 3.12-slim, non-root user
│   ├── requirements.txt
│   ├── agents/
│   │   ├── config.py              # ADK + Gemini + Composio key setup
│   │   ├── prompts.py             # Department-specific agent instructions
│   │   ├── router.py              # Department → agent factory dispatch
│   │   ├── runner.py              # ADK event loop + streaming wrapper
│   │   ├── tools.py               # Per-user Composio tool loader (cached)
│   │   ├── admin_agent.py
│   │   ├── sales_agent.py
│   │   ├── ops_agent.py
│   │   ├── finance_agent.py
│   │   └── executive_agent.py
│   ├── db/
│   │   ├── database.py            # SQLAlchemy engine, safe migrations
│   │   └── models.py              # User, ChatSession, ChatMessage, TokenBlacklist
│   ├── middleware/
│   │   └── rbac.py                # Cookie/Bearer JWT validation + blacklist check
│   ├── routers/
│   │   ├── auth.py                # Login, register, logout, user management
│   │   ├── chat.py                # Message handling, SSE streaming, document injection
│   │   ├── sessions.py            # Session CRUD, prompt templates
│   │   ├── upload.py              # File upload with text extraction
│   │   └── connectors.py          # Composio toolkit auth / status / disconnect
│   ├── services/
│   │   ├── auth_service.py        # Password hashing, JWT, blacklist, user CRUD
│   │   ├── prompt_engine.py       # Department-specific system prompts & templates
│   │   ├── summary_service.py     # Rolling session summary (Gemini-generated)
│   │   └── session_store.py       # Session & message persistence
│   └── tests/
│       ├── test_agents_config.py
│       ├── test_agents_router.py
│       ├── test_agents_runner.py
│       ├── test_agents_tools.py
│       └── test_summary_service.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Login page
│   │   │   ├── register/page.tsx  # Registration page
│   │   │   └── chat/page.tsx      # Main chat interface
│   │   └── lib/
│   │       ├── api.ts             # Backend API client
│   │       ├── auth-context.tsx   # Auth state management
│   │       └── themes.ts          # Department color themes
│   ├── next.config.ts             # Security headers, CSP
│   ├── Dockerfile                 # node:20-alpine, non-root user
│   └── package.json
├── docker-compose.yml             # Postgres + Backend + Frontend
├── .env.example                   # Template for environment variables
└── .gitignore
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key (https://openrouter.ai) |
| `COMPOSIO_API_KEY` | Yes* | — | Composio API key (*required for tool use*) |
| `JWT_SECRET` | Yes | — | Secret for signing JWTs (min 32 chars) |
| `ENVIRONMENT` | No | `development` | `development` or `production` — flips prod guards |
| `LLM_MODEL` | No | `google/gemini-3.5-flash` | OpenRouter model ID |
| `DATABASE_URL` | No | `sqlite:///./data/triton.db` | DB connection string (SQLite blocked in prod) |
| `CORS_ORIGINS` | No | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed origins |
| `FRONTEND_URL` | No | `http://localhost:3000` | Frontend URL for OAuth callbacks |
| `RATE_LIMIT_PER_MINUTE` | No | `30` | Global rate limit |
| `JWT_EXPIRE_HOURS` | No | `168` | Token expiry (default 7 days) |
| `COOKIE_SECURE` | No | `false` | `true` in production (HTTPS only) |
| `COOKIE_SAMESITE` | No | `lax` | `lax` same-site, `none` cross-site (requires Secure) |
| `COOKIE_DOMAIN` | No | *empty* | e.g. `.yourdomain.com` for cross-subdomain cookies |
| `UPLOAD_DIR` | No | `./data/uploads` | File upload directory |
| `POSTGRES_PASSWORD` | Docker | — | PostgreSQL password (Docker Compose only) |

---

## License

Proprietary. All rights reserved.
