# JobMail Android Mobile Deployment Guide

## Configured Android Application Settings

- **Application ID & Kotlin Package:** `com.jobmail.app` ([MainActivity.kt](frontend/android/app/src/main/kotlin/com/jobmail/app/MainActivity.kt))
- **Application Name:** `JobMail` ([AndroidManifest.xml](frontend/android/app/src/main/AndroidManifest.xml))
- **Minimum / Target SDK:** `minSdk = 24` (`flutter.minSdkVersion.coerceAtLeast(24)`), `targetSdk = 36` (`flutter.targetSdkVersion`) ([build.gradle.kts](frontend/android/app/build.gradle.kts))
- **Permissions:** `android.permission.INTERNET`, `android.permission.ACCESS_NETWORK_STATE`, and `<queries>` intents for `https`/`http` browsers (`url_launcher`)
- **Security Hardening:** `android:allowBackup="false"`, strict HTTPS network security policy by default ([network_security_config.xml](frontend/android/app/src/main/res/xml/network_security_config.xml)), encrypted Android Keystore tokens via `flutter_secure_storage`, zero Google secrets or refresh tokens in Flutter

---

## Prerequisites on This Windows Machine

1. **Install Android SDK (via Android Studio or Android SDK Command-Line Tools):**
   - Install Android Studio (includes Android SDK Platform, Build-Tools, and `platform-tools` / `adb`).
   - Set `ANDROID_HOME` (e.g., `%LOCALAPPDATA%\Android\Sdk`) and accept Android licenses:
     ```powershell
     flutter doctor --android-licenses
     flutter doctor -v
     ```
2. **Enable Windows Developer Mode (required for Flutter plugin symlinks during `flutter pub get`):**
   ```powershell
   start ms-settings:developers
   ```
   Toggle **Developer Mode** ON, then run:
   ```powershell
   cd d:\Email-identification\frontend
   flutter clean
   flutter pub get
   ```

---

## Building the Android APK

### Option A: Production Release APK (Enforces HTTPS Strictly)
```powershell
cd d:\Email-identification\frontend
flutter build apk --release --dart-define=JOBMAIL_API_URL=https://api.yourdomain.com
```
- Uses `network_security_config.xml` (cleartext HTTP disabled except loopback/emulator hosts).
- `ApiConfig` enforces HTTPS and locks custom endpoint editing when `JOBMAIL_API_URL` is set at compile time.

### Option B: Local Wi-Fi Physical-Device Testing APK
On the host PC (`192.168.1.6`), bind FastAPI to all network interfaces and ensure Windows Defender Firewall allows inbound TCP port `8000` on Private networks:
```powershell
cd d:\Email-identification\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Then build the APK with local HTTP explicitly enabled for private RFC1918 LAN IPs:
```powershell
cd d:\Email-identification\frontend
flutter build apk --release --dart-define=JOBMAIL_API_URL=http://192.168.1.6:8000 --dart-define=JOBMAIL_ALLOW_LOCAL_HTTP=true
```
- Passing `--dart-define=JOBMAIL_ALLOW_LOCAL_HTTP=true` enables BOTH `ApiConfig` private LAN IP validation AND `network_security_config_dev.xml` inside `build.gradle.kts`.
- Expected output file:
  `frontend/build/app/outputs/flutter-apk/app-release.apk`
- Optional smaller per-CPU-ABI APKs: add `--split-per-abi`.

### Production Play Store Signing (Optional)
1. Copy `frontend/android/key.properties.example` to `frontend/android/key.properties` (already ignored by `.gitignore`).
2. Generate your upload keystore (`keytool -genkey -v -keystore frontend/android/app/upload-keystore.jks ...`) and update `key.properties`. Never commit `.jks`, `.keystore`, or `key.properties`.

---

## Installing & Running on a Smartphone

### Method 1: USB Debugging + ADB
1. On Android phone: **Settings -> About phone -> Tap Build number 7 times -> Developer options -> Enable USB debugging**.
2. Connect USB cable and authorize the RSA fingerprint prompt.
3. Verify device detection and install:
   ```powershell
   adb devices
   adb install -r d:\Email-identification\frontend\build\app\outputs\flutter-apk\app-release.apk
   ```

### Method 2: Direct APK Transfer
1. Copy `frontend/build/app/outputs/flutter-apk/app-release.apk` to your phone via USB, Drive, or local share.
2. Tap the APK on your phone and allow **Install unknown apps** for your file manager/browser.

---

## Google OAuth 2.0 on Android

- **Why `http://localhost:8000/auth/google/callback` will NOT work from a real phone:** On a physical phone, `localhost` points to the phone itself rather than your PC, and Google OAuth rejects raw local Wi-Fi IPs (`192.168.1.6`).
- **Required Google Cloud Console & Backend Update:**
  1. Host the FastAPI backend behind a public **HTTPS** domain (or HTTPS reverse tunnel to port `8000` during testing).
  2. In **Google Cloud Console -> APIs & Services -> Credentials**, add your HTTPS callback to **Authorized redirect URIs**:
     `https://api.yourdomain.com/auth/google/callback`
  3. Set matching environment variables in `backend/.env` / deployment config:
     ```ini
     GOOGLE_REDIRECT_URI="https://api.yourdomain.com/auth/google/callback"
     ENVIRONMENT="production"
     COOKIE_SECURE="true"
     ```
  4. JobMail uses browser PKCE OAuth (`POST /auth/google/connect` -> Android system browser -> FastAPI HTTPS callback -> deep link `jobmail://oauth-callback?status=success` back into the app). `GOOGLE_CLIENT_SECRET` and encrypted refresh tokens remain exclusively on the backend.
