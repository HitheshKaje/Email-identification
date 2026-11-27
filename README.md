# JobMail – Intelligent Job Email Assistant

JobMail is a multi-account Gmail management and intelligent recruitment assistant built with **Flutter (Material Design 3)**, **FastAPI**, **MongoDB (Motor)**, **Google Gmail API (OAuth 2.0 read-only)**, **Scikit-learn (TF-IDF + Logistic Regression)**, and **Firebase Cloud Messaging (FCM)**.

## Project Structure

```text
Email-identification/
├── frontend/                  # Flutter mobile & web application (Material Design 3)
│   ├── lib/
│   │   ├── main.dart
│   │   ├── app.dart
│   │   ├── models/            # AuthSession, EmailItem, DashboardStats, ConnectedAccount, etc.
│   │   ├── providers/         # ChangeNotifier state management
│   │   ├── screens/           # Splash, Onboarding, Auth, Home, Inbox, Categories, Details, Accounts, Notifications, Settings
│   │   ├── services/          # Dio API client, repository & preferences persistence
│   │   ├── theme/             # Light & Dark Material 3 themes
│   │   ├── utils/             # API config, date formatter, responsive helpers
│   │   └── widgets/           # Reusable cards, badges, logo, adaptive NavigationBar/NavigationRail
│   ├── test/                  # Widget & navigation tests
│   └── pubspec.yaml
├── backend/                   # FastAPI REST API + OAuth + Gmail Sync + Background Scheduler
│   ├── app/
│   │   ├── main.py            # FastAPI app factory, CORS, lifespan & scheduler startup
│   │   ├── core/              # Settings, exceptions & safe request logging
│   │   ├── database/          # Motor async MongoDB client & unique/TTL indexes
│   │   ├── authentication/    # bcrypt, PyJWT, Fernet encryption, Google OAuth 2.0 HTTP client
│   │   ├── classification/    # Context baseline, entity extractor & TF-IDF NLP classifier
│   │   ├── notifications/     # Firebase Cloud Messaging (FCM) dispatcher
│   │   ├── background/        # Bounded periodic background sync scheduler
│   │   ├── models/            # Pydantic v2 schemas & domain enums
│   │   ├── services/          # Auth, OAuth, Gmail client/sync, Dashboard, Emails, Notifications, ML
│   │   └── api/               # Dependencies & REST routers
│   ├── tests/                 # Async pytest integration & ML suites
│   ├── .env.example
│   └── requirements.txt
├── ml/
│   ├── dataset/training_emails.json
│   ├── training/train_model.py
│   ├── models/email_classifier.joblib
│   └── predict.py
└── README.md
```

## Setup & Configuration

### 1. Google Cloud OAuth 2.0 (Read-Only Gmail)
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/) and enable the **Gmail API**.
2. Configure **Google Auth Platform / OAuth consent screen** with scope `https://www.googleapis.com/auth/gmail.readonly` and add test users while in Testing mode.
3. Create a **Web application** OAuth Client ID with authorized redirect URI `http://localhost:8000/auth/google/callback`.
4. Copy `backend/.env.example` to `backend/.env` and set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, strong `JWT_SECRET_KEY`, and Fernet `TOKEN_ENCRYPTION_KEY`. *(Never commit `backend/.env`.)*

### 2. Firebase Cloud Messaging (Optional Push Notifications)
- Place your Firebase Admin service account JSON path in `FIREBASE_CREDENTIALS_PATH` inside `backend/.env` (and install `firebase-admin` in `backend/.venv` when deploying push delivery). When unset, JobMail still stores deduplicated in-app notifications in MongoDB.

## Running Locally

### Backend (FastAPI + MongoDB + Background Sync)
```powershell
cd d:\Email-identification\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ..\ml\training\train_model.py
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend (Flutter Web / Mobile)
```powershell
cd d:\Email-identification\frontend
flutter pub get
flutter analyze --no-fatal-infos
flutter run -d web-server --web-hostname localhost --web-port 8080
```
