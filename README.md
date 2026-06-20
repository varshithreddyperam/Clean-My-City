# CleanMyCity - Enterprise AI Waste Management Grid

CleanMyCity is a modern, gamified, AI-powered waste management platform designed to motivate citizens to dispose of waste correctly and keep their city clean. The system verifies trash disposal using computer vision and awards points (XP) and badges to citizens based on their environmental contributions.

---

## 🌟 Key Features

### 1. Citizen Portal (Gamified Experience)
- **Account Sync & Auth:** Quick username-based synchronization simulating secure authentication.
- **Eco Balance Tracker:** Real-time tracking of points (XP), levels, progress bars, and achievements.
- **Earned Achievements:** Dynamic badge shelf (e.g., "Green Novice") that unlocks as citizens clean up the city.
- **AI Camera Upload & Map Verification:** Citizens can snap a photo of disposal containers or littered areas. The system uses geographic mapping (Leaflet.js) to pin the exact coordinates of waste disposal or reporting.

### 2. AI & Computer Vision Backend (OpenCV Preprocessing)
- **Grayscale Conversion & Canny Edge Detection:** Filters out noise and highlights boundaries to verify if the photo shows an object clearly.
- **Contour Framing Check:** Ensures the subject (the trash bin or trash item) is properly centered and scaled in the camera frame, rejecting low-quality or blank uploads.
- **Perceptual DHash (Difference Hash):** Prevents duplicate reporting spam by computing a 64-bit perceptual image hash and checking against recently submitted reports.
- **Automatic Classification:** Categorizes uploads into:
  - **Recyclable (50 XP):** Correctly sorted recycling (e.g., plastic bottles, aluminum cans).
  - **Non-Recyclable (20 XP):** General waste disposed of in standard bins.
  - **Littered (0 XP):** Loose garbage reported on streets/roads for cleanup.

### 3. Operations Dashboard (Ops Console)
- **Real-Time Data Feed:** Powered by a Server-Sent Events (SSE) stream that broadcasts live submissions and garbage reports to dispatch units instantly.
- **Interactive Heatmap:** Integrates Leaflet Maps to display live markers representing waste containers, recycling bins, and active cleanup alerts.
- **Operational Metrics:** Monitors total reports processed, edge density averages, and system health status.

---

## 🛠️ Technology Stack

- **Backend:** FastAPI (Python), Uvicorn (ASGI web server), SQLAlchemy (Async SQLite database operations), Python-Dotenv.
- **Computer Vision:** OpenCV (cv2), NumPy.
- **Frontend:** HTML5, CSS3 (Vanilla Custom Styles), Tailwind CSS (for grid layouts), Leaflet.js (interactive maps), FontAwesome Icons.
- **Eventing:** EventSource (Server-Sent Events) for real-time notifications.

---

## 📂 File Structure

```text
├── app/
│   ├── templates/
│   │   ├── assets/              # Static UI assets (clean_bin, litter_road, etc.)
│   │   ├── uploads/             # Directory where uploaded citizen photos are saved
│   │   ├── index.html           # Main frontend (Citizen & Admin UI views)
│   │   ├── main.js              # Frontend logic, map rendering, and SSE listener
│   │   └── style.css            # Custom cyber-themed styles and glassmorphism styling
│   ├── auth.py                  # Authentication helper logic
│   ├── cache.py                 # Duplicate prevention and upload cooldown manager
│   ├── database.py              # SQLite ORM models and initialization (SQLAlchemy)
│   ├── main.py                  # API endpoints, SSE stream controller, and app startup
│   ├── simulator.py             # Event broadcaster simulation
│   └── vision.py                # OpenCV image processing and mock classifier engine
├── backend/                     # Node.js secondary microservice
│   ├── data/
│   │   └── ledger.json          # Local file-based storage ledger
│   ├── database.js              # Mock backend db
│   ├── server.js                # Microservice routing
│   └── simulator.js             # Microservice simulation
├── requirements.txt             # Python dependencies
├── package.json                 # Node.js configuration
├── run.py                       # Application execution launcher
└── verify_tests.py              # Test verification script
```

---

## 🚀 Installation & Setup

1. **Clone/Download the repository** to your local workspace.
2. **Set up a Python Virtual Environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate     # On Windows
   # source .venv/bin/activate  # On macOS/Linux
   ```
3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Environment Variables:**
   Verify or create a `.env` file containing configuration keys (e.g. database URLs).
5. **Run the Application:**
   ```bash
   python run.py
   ```
6. **Access CleanMyCity:**
   Open your browser and navigate to `http://127.5.0.1:8000` (or the port output by the runner).
