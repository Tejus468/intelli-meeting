# Intelligent Meeting & Decision Intelligence System

## 1. Project Purpose
The Intelligent Meeting & Decision Intelligence System is designed to extract, organize, and query discussions, decisions, alternatives, and action items from meetings and documents using a hybrid knowledge graph and vector retrieval architecture.

## 2. Current Architecture
The current foundation consists of:
- **Backend**: FastAPI (Python) minimal API service exposing a health check endpoint.
- **Frontend**: Next.js (React + TypeScript) minimal application.
- **Database Layer (Docker Compose)**:
  - **PostgreSQL with pgvector**: For relational storage and vector embeddings.
  - **Neo4j Community Edition**: For knowledge graph relationships.

## 3. Required Software
- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- [Python 3.11+](https://www.python.org/)
- [Node.js 18+](https://nodejs.org/) and `npm`

---

## 4. Starting Infrastructure (PostgreSQL & Neo4j)

1. Copy the environment variables file:
   ```bash
   cp .env.example .env
   ```

2. Start the database containers with Docker Compose:
   ```bash
   docker compose up -d
   ```

3. Verify running containers:
   ```bash
   docker compose ps
   ```

Services will be accessible at:
- **PostgreSQL**: `localhost:5432`
- **Neo4j HTTP UI**: `http://localhost:7474`
- **Neo4j Bolt**: `bolt://localhost:7687`

To stop the services:
   ```bash
   docker compose down
   ```

---

## 5. Running the FastAPI Backend Locally

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

5. Verify the health check:
   - Endpoint: `http://127.0.0.1:8000/health`
   - API Docs: `http://127.0.0.1:8000/docs`

---

## 6. Running the Next.js Frontend Locally

1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the Next.js development server:
   ```bash
   npm run dev
   ```

4. Open `http://localhost:3000` in your browser.
