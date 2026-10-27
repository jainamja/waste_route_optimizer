# 🚛 OnRoute — Waste Collection Route Optimizer & Live Fleet Tracking Platform

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![OR-Tools](https://img.shields.io/badge/Google-OR--Tools-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://developers.google.com/optimization)
[![Firebase](https://img.shields.io/badge/Firebase-Realtime%20Database-FFCA28?style=for-the-badge&logo=firebase&logoColor=black)](https://firebase.google.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Android](https://img.shields.io/badge/Android-Native%20Service-3DDC84?style=for-the-badge&logo=android&logoColor=white)](https://developer.android.com/)

**OnRoute** is an intelligent waste collection route optimizer and real-time fleet telemetry platform. It solves complex Vehicle Routing Problems (VRP) using **Google OR-Tools**, balances customer stop workloads across available trucks, and streams live GPS tracking to dispatchers and field drivers via **Firebase Realtime Database**.

---

## 📸 Screenshots

<!-- Place your product screenshots here -->
| Admin Operations Deck | Route Planning & Upload | Driver Mobile App |
| :---: | :---: | :---: |
| ![Admin Operations Deck](docs/screenshots/dashboard.png) | ![Route Planning & Upload](docs/screenshots/upload.png) | ![Driver Mobile App](docs/screenshots/driver.png) |
*Place dashboard, planning, and driver screenshots in `docs/screenshots/`.*

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Clients["Clients"]
        Admin["Admin Dispatch Dashboard\n(Web Browser / Leaflet Map)"]
        Driver["Driver Mobile App\n(Android Foreground Service / Web PWA)"]
    end

    subgraph Backend["Flask Core Application (waste_route_optimizer.py)"]
        Auth["Admin Session Auth & Driver Token Guard"]
        DataIngest["Customer Data Ingestion\n(Excel / CSV / DOCX)"]
        APIs["REST API Endpoints\n(/api/data, /api/mark_completed, /api/dynamic_recalculate)"]
    end

    subgraph Optimization["Optimization Engine (aco_vrp.py)"]
        VRP["Google OR-Tools RouteOptimizer\n(Capacity, Service Times, Workload Balancing)"]
        Matrix["Distance Matrix Provider\n1. Google Maps Matrix API (with retry)\n2. OSRM Road Table API\n3. Geodesic Fallback"]
    end

    subgraph External["External Infrastructure & Storage"]
        DB[("Database\nPostgreSQL (Production) / SQLite (Local)")]
        Firebase[("Firebase Realtime Database\n(Sub-second Driver Telemetry & Token Caching)")]
        MapsAPI["Google Maps / OSRM Routing Engine"]
    end

    Admin -->|Login & Dispatch Actions| Auth
    Driver -->|Stream GPS & Complete Stops| APIs
    Auth --> APIs
    DataIngest --> APIs
    APIs -->|Trigger Solve| VRP
    VRP --> Matrix
    Matrix --> MapsAPI
    APIs -->|Persist Routes & Stops| DB
    APIs -->|Sync Route Changes| Firebase
    Driver -->|High-Frequency GPS (1.5s)| Firebase
    Firebase -->|Live Marker Updates (60fps)| Admin
```

---

## ✨ Core Features

### 1. 🧠 Algorithmic Route Optimization (`RouteOptimizer`)
- **OR-Tools VRP Solver:** Solves Capacitated Vehicle Routing Problems (CVRP) with multiple vehicle starts/ends and stop balance constraints.
- **Dynamic Truck Capping:** Prevents solver infeasibility when `num_trucks > customers` by automatically bounding truck allocation and allowing 0 minimum stops.
- **Optional Capacity Constraints:** Enforces truck load limits if customer waste weight (`waste_kg`) and vehicle capacity are provided.
- **Configurable Service Time:** Adjusts per-stop collection dwell time (defaults to 5 minutes) to calculate accurate shift durations.
- **Fault-Tolerant Road Routing:** Evaluates turn-by-turn road matrices via Google Maps Distance Matrix with automated single-chunk retry, falling back to OSRM and geodesic distance.

### 2. 📍 Real-Time Fleet Telemetry
- **Sub-Second Streaming:** Receives 1.5-second vehicle coordinates via Firebase Realtime Database.
- **Smooth 60 FPS Gliding:** Uses linear interpolation (lerp) on the Leaflet dashboard map to prevent marker teleportation.
- **Road Centerline Snapping:** 65-meter tolerance snaps drift-prone GPS signals to urban street geometry.
- **Bearing Orientation:** Vehicle icons rotate dynamically according to travel heading.
- **Forward-Only Navigation Display:** Automatically clears past collection legs once reached.

### 3. 📱 Driver Mobile Experience & Security
- **Independent Driver Tokens:** Field drivers authenticate using individual per-truck tokens (`driver_tokens`) without needing administrative session credentials.
- **Android Background Service:** Continuous GPS foreground service (`LocationService.java`) keeps telemetry alive even when the phone is locked or Google Maps navigation is active.
- **Instant Re-Routing:** Drivers can mark stops completed or skipped, triggering dynamic route recalculation for remaining stops.

---

## 🛠️ Required Environment Variables

All sensitive credentials and database configurations are loaded from environment variables using `python-dotenv`. Create a `.env` file in the project root:

| Variable | Required | Default / Example | Purpose |
| :--- | :---: | :--- | :--- |
| `SECRET_KEY` | **Yes** | `your-secure-random-secret-key` | Signs Flask session cookies for admin authentication. |
| `ADMIN_PASSWORD_HASH` | **Yes** | `scrypt:32768:8:1$...` | Werkzeug password hash for admin login (`/login`). |
| `FIREBASE_API_KEY` | **Yes** | `AIzaSy...` | Firebase Web API Key used for anonymous identity tokens. |
| `FIREBASE_DB_URL` | **Yes** | `https://<project>-default-rtdb.firebaseio.com` | Base URL of your Firebase Realtime Database. |
| `DATABASE_URL` | No | `sqlite:///instance/routes.db` | PostgreSQL connection string (Render, Supabase, Neon) or local SQLite. |
| `GMAPS_API_KEY` | No | `AIzaSy...` | Optional Google Maps API key for distance matrix and geocoding. |
| `PORT` | No | `5000` | Port for the local or container web server. |

### Generating the Admin Password Hash

Run this one-line command to generate an administrative password hash:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your_chosen_admin_password'))"
```

Copy the generated hash and paste it into `.env` as `ADMIN_PASSWORD_HASH`.

---

## 🚀 Setup & Installation

### Prerequisites
- **Python 3.10+**
- **pip** and **virtualenv**
- (Optional) **Node.js 18+** & **Android Studio** for compiling the Android driver APK.

### 1. Clone & Set Up Python Environment

```bash
# Clone the repository
git clone https://github.com/jainamja/waste_route_optimizer.git
cd waste_route_optimizer

# Create and activate virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Linux / macOS:
source venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the provided example environment template:

```bash
cp .env.example .env
```

Edit `.env` with your actual Firebase URL, Firebase API key, and admin password hash.

---

## 💻 Running Locally

Start the local Flask development server:

```bash
python waste_route_optimizer.py
```

The application will start on `http://127.0.0.1:5000`.
- Open `http://localhost:5000/login` in your web browser.
- Log in with the admin password you hashed in `.env`.
- Upload your customer schedule (e.g. `customers.xlsx`), configure starting depots, truck count, optional capacity and service time, and click **Optimize Routes**.

---

## 🌐 Production Deployment (Gunicorn)

For production Linux environments (e.g. Render, AWS EC2, DigitalOcean, Railway), serve the application using **Gunicorn**:

```bash
# Using the bundled configuration file:
gunicorn -c gunicorn.conf.py waste_route_optimizer:app

# Or directly with custom workers and binding:
gunicorn -w 4 -k gthread --threads 4 -b 0.0.0.0:5000 --timeout 120 waste_route_optimizer:app
```

### Render Deployment Quick-Start
- **Environment:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -c gunicorn.conf.py waste_route_optimizer:app`
- **Environment Variables:** Set `SECRET_KEY`, `ADMIN_PASSWORD_HASH`, `FIREBASE_API_KEY`, `FIREBASE_DB_URL`, and `DATABASE_URL` in the Render dashboard.

---

## 🧪 Running Tests

The test suite is built with **pytest** and covers coordinate extraction, CSV/XLSX file ingestion, and OR-Tools routing engine constraints:

```bash
python -m pytest tests -v
```

All 16 tests run completely offline with mocked HTTP routing endpoints to verify:
- Comma-separated and negative latitude/longitude coordinate parsing.
- CSV and Excel parsing with custom stop loads and column variations.
- Cap on trucks when `num_trucks > customers` (Phase 3 solver stability).
- Vehicle capacity constraints (Phase 5).
- Service time calculations (Phase 5).
- Clean `ValueError` exception raising instead of raw assertion errors.

---

## ⚠️ System Limitations & Operational Considerations

1. **Routing Matrix Rate Limits:**
   - When `GMAPS_API_KEY` is omitted, route matrix calculations query the public Open Source Routing Machine (`router.project-osrm.org`) or geodesic fallback. Public OSRM servers are subject to community rate limits and network latency. For enterprise scale without Google Maps billing, host a dedicated local OSRM instance.
2. **Driver Cellular Connectivity:**
   - High-frequency GPS updates depend on active mobile data. If a driver enters a cellular dead zone, location updates pause until data connectivity is restored; stop completions are queued locally.
3. **In-Memory Solver Scale:**
   - OR-Tools calculates optimal routes synchronously in memory within an 8-second Guided Local Search window. Route batches with more than 500 stops per single solve should increase the search time limit or partition stops into regional sectors before optimization.
4. **Firebase Realtime Database Bandwidth:**
   - 1.5-second live streaming from dozens of active vehicles produces continuous concurrent connections. Ensure your Firebase project plan accommodates the required simultaneous connection count and monthly bandwidth.

---

## 📄 License
This project is licensed under the ISC License. See the [LICENSE](LICENSE) file for details.
