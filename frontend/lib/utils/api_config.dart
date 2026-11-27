import 'package:flutter/foundation.dart';

/// Centralized API configuration enforcing HTTPS in production while supporting
/// local development loopback, Android emulator, and private LAN IPs in dev/test builds.
class ApiConfig {
  ApiConfig._();

  static const String _envBaseUrl = String.fromEnvironment('JOBMAIL_API_URL');
  static const bool allowLocalHttp =
      bool.fromEnvironment('JOBMAIL_ALLOW_LOCAL_HTTP', defaultValue: false);

  static bool get allowLocalHttpInCurrentBuild =>
      !kReleaseMode || allowLocalHttp;

  static bool get canCustomizeApiUrl =>
      allowLocalHttpInCurrentBuild || _envBaseUrl.isEmpty;

  static String get endpointHint => allowLocalHttpInCurrentBuild
      ? 'http://192.168.1.6:8000 or https://api.yourdomain.com'
      : 'https://api.yourdomain.com';

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

  /// Returns true when [host] is a loopback host, Android emulator host,
  /// `.local` mDNS host, or an RFC1918 private LAN IPv4 address.
  static bool isLocalOrPrivateHost(String host) {
    final normalized = host.trim().toLowerCase();
    if (normalized.isEmpty) {
      return false;
    }
    const loopbackHosts = <String>{'localhost', '127.0.0.1', '10.0.2.2'};
    if (loopbackHosts.contains(normalized) || normalized.endsWith('.local')) {
      return true;
    }
    final parts = normalized.split('.');
    if (parts.length != 4) {
      return false;
    }
    final octets = parts.map(int.tryParse).toList();
    if (octets.any((octet) => octet == null || octet < 0 || octet > 255)) {
      return false;
    }
    final a = octets[0]!;
    final b = octets[1]!;
    if (a == 10) {
      return true;
    }
    if (a == 192 && b == 168) {
      return true;
    }
    if (a == 172 && b >= 16 && b <= 31) {
      return true;
    }
    return false;
  }

  /// Validates that public release builds only use HTTPS, while development or
  /// explicit LAN-testing builds also permit HTTP strictly for local/private hosts.
  static bool isValidEndpointUrl(String rawUrl) {
    final uri = Uri.tryParse(rawUrl.trim());
    if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
      return false;
    }
    final scheme = uri.scheme.toLowerCase();
    if (scheme == 'https') {
      return true;
    }
    if (allowLocalHttpInCurrentBuild && scheme == 'http') {
      return isLocalOrPrivateHost(uri.host);
    }
    return false;
  }

  static const Duration connectTimeout = Duration(seconds: 12);
  static const Duration receiveTimeout = Duration(seconds: 20);
}
