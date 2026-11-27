import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Platform-aware encrypted credential storage backed by Keychain/Keystore/DPAPI on native targets.
class SecureTokenStorage {
  SecureTokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const String _keyAccessToken = 'jobmail_secure_access_token';
  static const String _keyRefreshToken = 'jobmail_secure_refresh_token';
  static const String _keySessionId = 'jobmail_secure_session_id';

  // On Flutter Web, rely on HttpOnly cookies + in-memory short-lived access tokens cleanly.
  String? _webMemoryAccessToken;
  String? _webMemorySessionId;

  Future<String?> readAccessToken() async {
    if (kIsWeb) return _webMemoryAccessToken;
    try {
      return await _storage.read(key: _keyAccessToken);
    } catch (_) {
      return _webMemoryAccessToken;
    }
  }

  Future<String?> readRefreshToken() async {
    if (kIsWeb) return null;
    try {
      return await _storage.read(key: _keyRefreshToken);
    } catch (_) {
      return null;
    }
  }

  Future<String?> readSessionId() async {
    if (kIsWeb) return _webMemorySessionId;
    try {
      return await _storage.read(key: _keySessionId);
    } catch (_) {
      return _webMemorySessionId;
    }
  }

  Future<void> writeTokens({
    required String? accessToken,
    required String? refreshToken,
    required String? sessionId,
  }) async {
    _webMemoryAccessToken = accessToken;
    _webMemorySessionId = sessionId;
    if (kIsWeb) return;

    try {
      if (accessToken == null || accessToken.isEmpty) {
        await _storage.delete(key: _keyAccessToken);
      } else {
        await _storage.write(key: _keyAccessToken, value: accessToken);
      }
      if (refreshToken == null || refreshToken.isEmpty) {
        await _storage.delete(key: _keyRefreshToken);
      } else {
        await _storage.write(key: _keyRefreshToken, value: refreshToken);
      }
      if (sessionId == null || sessionId.isEmpty) {
        await _storage.delete(key: _keySessionId);
      } else {
        await _storage.write(key: _keySessionId, value: sessionId);
      }
    } catch (_) {
      // Fallback safely in headless test harnesses without platform channels.
    }
  }

  Future<void> clearAll() async {
    _webMemoryAccessToken = null;
    _webMemorySessionId = null;
    if (kIsWeb) return;
    try {
      await _storage.delete(key: _keyAccessToken);
      await _storage.delete(key: _keyRefreshToken);
      await _storage.delete(key: _keySessionId);
    } catch (_) {}
  }
}
