# 🚛 OnRoute — Intelligent Waste Route Optimizer & Live Fleet Tracking Platform

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Android](https://img.shields.io/badge/Android-Native%20Service-3DDC84?style=for-the-badge&logo=android&logoColor=white)](https://developer.android.com/)
[![Capacitor](https://img.shields.io/badge/Capacitor-8.x-119EFF?style=for-the-badge&logo=capacitor&logoColor=white)](https://capacitorjs.com/)
[![Firebase](https://img.shields.io/badge/Firebase-Realtime%20Database-FFCA28?style=for-the-badge&logo=firebase&logoColor=black)](https://firebase.google.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![OSRM](https://img.shields.io/badge/OSRM-Routing%20Engine-4CAF50?style=for-the-badge)](http://project-osrm.org/)

**OnRoute** is an enterprise-grade fleet management, algorithmic route optimization, and real-time telemetry platform tailored for commercial waste management and urban collection operations.

It combines combinatorial optimization algorithms (Ant Colony Optimization & Google OR-Tools) with sub-second live GPS tracking modeled after ride-hailing platforms like Uber and Ola.

---

## 📸 Key Capabilities & Architecture

```
                       ┌─────────────────────────────────────────┐
                       │     Admin Dispatch Web Dashboard        │
                       │  (Fleet Control, Route Scheduling,      │
                       │   60fps Live Tracker, Messenger)        │
                       └────────────────────┬────────────────────┘
                                            │
                                            ▼
                       ┌─────────────────────────────────────────┐
                       │       Flask REST & Optimization API     │
                       │  (ACO Algorithm, OR-Tools VRP Solver,   │
                       │   PostgreSQL Storage, Template Engine)  │
                       └───────────┬─────────────────┬───────────┘
                                   │                 │
                OSRM Distance Matrix│                 │Realtime Sync
                                   ▼                 ▼
                       ┌──────────────────┐   ┌───────────────────────────┐
                       │ OSRM Road Router │   │ Firebase Realtime Database│
                       └──────────────────┘   └─────────────┬─────────────┘
                                                            │ Sub-second Telemetry
                                                            ▼
                                              ┌───────────────────────────┐
                                              │  Android Native Driver App│
                                              │(1.5s GPS Foreground Serv, │
                                              │ Navigation, Sub-stops)    │
                                              └───────────────────────────┘
```

---

## ✨ Features

### 1. 🧠 Algorithmic Route Optimization (VRP Engine)
- **Hybrid Solvers:** Employs **Ant Colony Optimization (ACO)** and **Google OR-Tools** to solve complex Vehicle Routing Problems with capacity constraints and time windows.
- **Turn-by-Turn Road Matrix:** Uses real-world road network geometry from **OSRM (Open Source Routing Machine)** rather than straight-line Euclidean distance.
- **Multi-Vehicle Load Balancing:** Evenly distributes customer stops across truck capacities, maximizing fuel efficiency and eliminating redundant mileage.

### 2. 📍 Uber / Ola-Grade Live Fleet Tracker
- **High-Frequency GPS Streaming:** 1.5-second live telemetry broadcasted directly from driver devices.
- **60 FPS Smooth Interpolation:** Employs `requestAnimationFrame` linear interpolation (lerp) so truck markers glide smoothly along streets without jumpy teleportation.
- **Smart Urban Road-Snapping (Map-Matching):** Snaps vehicle positions to the nearest active road centerline with a 65-meter tolerance, preventing GPS multipath drift into adjacent buildings.
- **Directional Bearing Rotation:** Marker rotates dynamically (`transform: rotate(...)`) to match travel direction and street angles.
- **Forward-Only Navigation Display:** Automatically prunes past route legs once reached, displaying only the active journey ahead of the vehicle.

### 3. 📱 Driver Mobile App (Android Native & Capacitor PWA)
- **Background GPS Foreground Service (`LocationService.java`):** Continuous tracking persists even when the driver locks the screen, minimizes the app, or navigates in Google Maps.
- **Atomic Multi-Path Sync:** Merges driver location and truck node updates into a single HTTP PATCH with persistent `Keep-Alive`, cutting battery and cell data consumption.
- **One-Tap Turn-by-Turn Navigation:** Launches Google Maps navigation directly to the next stop with a single tap.
- **Sub-Stop Clustering & Actionable Stops:** Groups multiple customers at the same gate/society into unified clusters with individual and bulk complete/skip actions.
- **Offline Resilience:** Optimistic UI updates with queued WebSocket syncing and HTTP keepalive fallbacks.

### 4. 🗓️ Schedule & Template Management
- **Recurring Route Templates:** Save, clone, and isolate day-specific route schedules (e.g., Monday Route, Tuesday Route).
- **Manual Stop Customization:** Reorder stop sequences on the fly, toggle customer status (Active / Inactive), and assign trucks dynamically.
- **Real-Time Customer Verification:** Search customer collection histories, update contact numbers, and record skip reasons.

### 5. 💬 Instant Two-Way Dispatch Messenger
- **Priority Heads-Up Alerts:** Dispatches urgent audio alerts and full-screen Android notifications to drivers on duty.
- **Read Receipts:** Dispatchers see real-time delivery and read timestamps for operational transparency.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend & API** | Python 3.10+, Flask, Flask-SQLAlchemy, Gunicorn |
| **Optimization** | Google OR-Tools, Custom Ant Colony Optimization (`aco_vrp.py`) |
| **Routing & GIS** | OSRM (Open Source Routing Machine), Leaflet.js, Geopy |
| **Live Telemetry** | Firebase Realtime Database (Google Cloud) |
| **Database** | PostgreSQL (Production) / SQLite (Local Dev) |
| **Mobile Application** | Capacitor 8, Native Java Android Foreground Service, HTML5 / CSS3 / ES6 |
| **Hosting & Cloud** | Render Web Services, Hostinger DNS, Custom Domains (SSL / HTTPS) |

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10 or higher
- Node.js 18+ and npm
- Android Studio (for native Android builds)
- Firebase Project with Realtime Database enabled

---

### Backend Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jainamja/waste_route_optimizer.git
   cd waste_route_optimizer
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Create a `.env` file or set environment variables:
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/wasteroute_db
   SECRET_KEY=your-super-secret-key
   PORT=5000
   ```

5. **Run database migrations & start development server:**
   ```bash
   python waste_route_optimizer.py
   ```
   The web dashboard will be available at `http://localhost:5000`.

---

### Mobile App Setup (Android)

1. **Install Capacitor CLI and npm packages:**
   ```bash
   npm install
   ```

2. **Synchronize web assets into Android project:**
   ```bash
   npx cap sync android
   ```

3. **Open in Android Studio or build debug APK directly:**
   ```bash
   cd android
   # On Windows:
   .\gradlew.bat assembleDebug
   # On Linux/macOS:
   ./gradlew assembleDebug
   ```
   The compiled APK will be output at:
   `android/app/build/outputs/apk/debug/app-debug.apk`

---

## 🌐 Custom Domain & Deployment

The platform is optimized for zero-downtime deployment on **Render**:

1. **Web Service Setup:**
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -c gunicorn.conf.py waste_route_optimizer:app`

2. **Custom Domain:**
   - Point a `CNAME` record from your domain registrar (e.g., `app.greenglobalyx.com`) to your Render service address (`waste-route-optimizer-robn.onrender.com`).
   - Render automatically provisions and renews SSL/TLS certificates via Let's Encrypt.

---

## 📁 Repository Structure

```
waste_route_optimizer/
├── aco_vrp.py                  # Ant Colony Optimization vehicle routing algorithm
├── waste_route_optimizer.py    # Flask application core, routes, and database models
├── gunicorn.conf.py            # Production WSGI server configuration
├── requirements.txt            # Python dependencies
├── package.json                # Capacitor and frontend dependencies
├── capacitor.config.json       # Mobile application app ID and navigation whitelist
├── android/                    # Native Android Studio project
│   └── app/src/main/java/com/wasteroute/driver/
│       ├── MainActivity.java   # Android wrapper entry point
│       └── LocationService.java# High-frequency native GPS foreground service
├── src/                        # Mobile app web client (HTML5/CSS3/JS)
│   └── index.html              # Driver interface with native bridge
├── templates/                  # Admin dispatch templates (Jinja2)
│   ├── live_tracking.html      # 60fps Leaflet real-time fleet tracker
│   ├── driver_view.html        # Web-based driver route interface
│   └── ...                     # Route optimizer, saved templates, customer management
└── static/                     # Shared CSS stylesheets, icons, and client scripts
```

---

## 🔒 Security & Privacy
- **Role-Based Access Control:** Distinct permission boundaries between Dispatch Administrators and Field Drivers.
- **Secure Anonymous Auth:** Automated identity token expiration checks and renewal against Google Identity Toolkit.
- **GPS Privacy Boundaries:** Tracking automatically shuts down upon completing the final collection stop or logging out.

---

## 📄 License
This project is licensed under the ISC License. See the [LICENSE](LICENSE) file for details.

---

*Engineered with precision for zero-waste, high-efficiency fleet logistics.*
