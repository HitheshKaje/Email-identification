# JobMail – Intelligent Job Email Assistant

JobMail is a mobile-first intelligent email management application designed to automatically identify, classify, and surface career-related emails (job opportunities, internships, interviews, online assessments, recruitment drives, offer letters, application updates, and rejections) from multiple Gmail accounts.

## Project Structure

```text
Email-identification/
├── frontend/                  # Flutter mobile application (Material Design 3)
│   ├── lib/
│   │   ├── main.dart
│   │   ├── app.dart
│   │   ├── models/            # Domain models & category enums
│   │   ├── providers/         # ChangeNotifier state management
│   │   ├── screens/           # All 9 screens + category drill-down
│   │   ├── services/          # Dio API client, repository & preferences
│   │   ├── theme/             # Light & Dark Material 3 themes
│   │   ├── utils/             # API config, date formatter, responsive helpers
│   │   └── widgets/           # Reusable UI cards, logo, badges, nav shell
│   ├── test/                  # Widget & navigation tests
│   ├── analysis_options.yaml
│   └── pubspec.yaml
├── backend/                   # (Phase 2+) FastAPI + MongoDB + OAuth + Gmail + ML + FCM
├── ml/                        # (Phase 5) Dataset, training & classification models
└── README.md
```

## Development Phases

- **Phase 1 (Current):** Complete Flutter UI with 9 screens, Material 3 light/dark themes, responsive layout (`NavigationBar` / `NavigationRail`), reusable widgets, `Provider` state management, centralized `Dio` repository layer, and widget tests.
- **Phase 2:** FastAPI backend, MongoDB connection, JWT auth, and core REST endpoints.
- **Phase 3:** Google OAuth 2.0 & multi-account Gmail integration (read-only).
- **Phase 4:** Incremental Gmail synchronization & background worker.
- **Phase 5:** NLP email classification engine (TF-IDF + Scikit-learn + feedback loop).
- **Phase 6:** Firebase Cloud Messaging (FCM) push notifications.
- **Phase 7:** End-to-end testing, security hardening, and documentation.
