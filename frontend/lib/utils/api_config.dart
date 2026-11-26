import 'package:flutter/foundation.dart';

/// Centralized API configuration for JobMail backend communication.
class ApiConfig {
  ApiConfig._();

  static const String _envBaseUrl = String.fromEnvironment('JOBMAIL_API_URL');

  /// Default base URL tailored per platform for local development,
  /// overridable via `--dart-define=JOBMAIL_API_URL=https://api.example.com`.
  static String get defaultBaseUrl {
    if (_envBaseUrl.isNotEmpty) {
      return _envBaseUrl;
    }
    if (kIsWeb) {
      return 'http://localhost:8000';
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'http://10.0.2.2:8000';
      default:
        return 'http://localhost:8000';
    }
  }

  static const Duration connectTimeout = Duration(seconds: 12);
  static const Duration receiveTimeout = Duration(seconds: 20);
}
