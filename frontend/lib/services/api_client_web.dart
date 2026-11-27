import 'package:dio/browser.dart';
import 'package:dio/dio.dart';
import 'package:web/web.dart' as web;

void configureDioForPlatform(Dio dio) {
  dio.httpClientAdapter = BrowserHttpClientAdapter(withCredentials: true);
}

String? readCsrfCookieToken() {
  final raw = web.document.cookie;
  if (raw.isEmpty) return null;
  for (final pair in raw.split(';')) {
    final trimmed = pair.trim();
    if (trimmed.startsWith('jobmail_csrf_token=')) {
      return Uri.decodeComponent(
        trimmed.substring('jobmail_csrf_token='.length),
      );
    }
  }
  return null;
}
