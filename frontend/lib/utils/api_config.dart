import 'package:flutter/foundation.dart';

/// Centralized API configuration enforcing HTTPS outside local development.
class ApiConfig {
  ApiConfig._();

  static const String _envBaseUrl = String.fromEnvironment('JOBMAIL_API_URL');

  static bool get canCustomizeApiUrl => !kReleaseMode;

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

  /// Validates that release builds only talk over HTTPS and dev builds only use localhost over HTTP.
  static bool isValidEndpointUrl(String rawUrl) {
    final uri = Uri.tryParse(rawUrl.trim());
    if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
      return false;
    }
    final scheme = uri.scheme.toLowerCase();
    if (scheme == 'https') {
      return true;
    }
    if (!kReleaseMode && scheme == 'http') {
      const devHosts = <String>{'localhost', '127.0.0.1', '10.0.2.2'};
      return devHosts.contains(uri.host.toLowerCase());
    }
    return false;
  }

  static const Duration connectTimeout = Duration(seconds: 12);
  static const Duration receiveTimeout = Duration(seconds: 20);
}
