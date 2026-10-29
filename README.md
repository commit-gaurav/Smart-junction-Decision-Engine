# Smart Junction Decision Engine

An explainable traffic junction decision engine and dashboard for a simulated four-way intersection (North, East, South, West).

> **SAFETY NOTICE:** This project is a software simulation and does not transmit instructions to hardware or physical traffic equipment. All timings and configurations are editable software-demo values and do not constitute certified road-engineering guidance.

## Architecture

- **Backend**: Python + FastAPI, SQLite database, Pydantic settings and schemas.
- **Frontend**: React (Vite-compatible SPA).
- **Domain Scope**: Single 4-way junction with mutually exclusive NESW phases, bounded green allocations, fairness wait ceiling, and operator-confirmed emergency prioritization.

## Project Structure

```text
.
├── PLAN.md                  # Project plan and specifications
├── README.md                # Project documentation and instructions
├── .gitignore               # Ignored artifacts (DBs, uploads, node_modules, envs)
├── .env.example             # Environment variable templates and defaults
├── backend/
│   ├── requirements.txt     # Python dependencies
│   └── app/
│       ├── config.py        # Centralized settings and demo defaults
│       └── main.py          # FastAPI application entry point
└── frontend/
    ├── package.json         # React & tooling dependencies
    ├── index.html           # SPA entry point
    └── src/
        ├── main.jsx         # React application root mount
        └── App.jsx          # Root application component
```

## Getting Started

### 1. Backend Setup

Prerequisites: Python 3.10+

```bash
cd backend
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate

# On Windows PowerShell (Standard Python from python.org):
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
# .\.venv\Scripts\Activate.ps1

# On Windows PowerShell (MSYS2 / UCRT64 Python):
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
# .\.venv\bin\Activate.ps1

# Or run directly without activating:
# .\.venv\bin\python.exe -m pip install -r requirements.txt
# .\.venv\bin\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend health check will be available at: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
API documentation will be available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. Frontend Setup

Prerequisites: Node.js 18+ and npm

```bash
cd frontend
npm install
npm run dev
```

The React frontend interface will be available at: [http://localhost:5173](http://localhost:5173)

