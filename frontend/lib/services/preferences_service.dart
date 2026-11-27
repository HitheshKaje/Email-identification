import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/notification_preferences.dart';
import '../utils/api_config.dart';
import 'secure_token_storage.dart';

/// Persists non-sensitive UI preferences in SharedPreferences and delegates tokens to SecureTokenStorage.
class PreferencesService {
  PreferencesService(
    this._prefs, {
    SecureTokenStorage? secureStorage,
  }) : _secureStorage = secureStorage ?? SecureTokenStorage() {
    final legacy = _prefs.getString(_keyAuthToken);
    if (legacy != null && legacy.trim().isNotEmpty) {
      _cachedAuthToken = legacy.trim();
    }
  }

  final SharedPreferences _prefs;
  final SecureTokenStorage _secureStorage;

  String? _cachedAuthToken;
  String? _cachedRefreshToken;
  String? _cachedSessionId;

  static const String _keyOnboardingDone = 'jobmail_onboarding_done';
  static const String _keyThemeMode = 'jobmail_theme_mode';
  static const String _keyAutoSync = 'jobmail_auto_sync';
  static const String _keySyncIntervalMins = 'jobmail_sync_interval_mins';
  static const String _keyProfileName = 'jobmail_profile_name';
  static const String _keyProfileEmail = 'jobmail_profile_email';
  static const String _keyApiUrl = 'jobmail_api_url';
  static const String _keyNotifPrefs = 'jobmail_notif_prefs';
  static const String _keyAuthToken = 'jobmail_auth_token';

  /// Hydrates encrypted native tokens and purges any legacy plaintext SharedPreferences token.
  Future<void> initSecureSession() async {
    final storedAccess = await _secureStorage.readAccessToken();
    final storedRefresh = await _secureStorage.readRefreshToken();
    final storedSid = await _secureStorage.readSessionId();
    if (storedAccess != null && storedAccess.isNotEmpty) {
      _cachedAuthToken = storedAccess;
      _cachedRefreshToken = storedRefresh;
      _cachedSessionId = storedSid;
    } else if (_cachedAuthToken != null && !kIsWeb) {
      await _secureStorage.writeTokens(
        accessToken: _cachedAuthToken,
        refreshToken: _cachedRefreshToken,
        sessionId: _cachedSessionId,
      );
    }
    if (_prefs.containsKey(_keyAuthToken)) {
      await _prefs.remove(_keyAuthToken);
    }
  }

  bool get isOnboardingCompleted => _prefs.getBool(_keyOnboardingDone) ?? false;

  Future<void> setOnboardingCompleted(bool value) =>
      _prefs.setBool(_keyOnboardingDone, value);

  ThemeMode get themeMode {
    final raw = _prefs.getString(_keyThemeMode);
    switch (raw) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }

  Future<void> setThemeMode(ThemeMode mode) {
    final raw = switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
    };
    return _prefs.setString(_keyThemeMode, raw);
  }

  bool get autoSyncEnabled => _prefs.getBool(_keyAutoSync) ?? true;

  Future<void> setAutoSyncEnabled(bool enabled) =>
      _prefs.setBool(_keyAutoSync, enabled);

  int get syncIntervalMinutes => _prefs.getInt(_keySyncIntervalMins) ?? 15;

  Future<void> setSyncIntervalMinutes(int minutes) =>
      _prefs.setInt(_keySyncIntervalMins, minutes);

  String get profileName => _prefs.getString(_keyProfileName) ?? 'Candidate';

  Future<void> setProfileName(String name) =>
      _prefs.setString(_keyProfileName, name.trim());

  String get profileEmail => _prefs.getString(_keyProfileEmail) ?? '';

  Future<void> setProfileEmail(String email) =>
      _prefs.setString(_keyProfileEmail, email.trim());

  String get apiBaseUrl {
    final saved = _prefs.getString(_keyApiUrl);
    if (saved != null && ApiConfig.isValidEndpointUrl(saved)) {
      return saved;
    }
    return ApiConfig.defaultBaseUrl;
  }

  Future<void> setApiBaseUrl(String url) {
    final cleaned = url.trim();
    if (!ApiConfig.isValidEndpointUrl(cleaned)) {
      return Future<void>.value();
    }
    return _prefs.setString(_keyApiUrl, cleaned);
  }

  NotificationPreferences get notificationPreferences {
    final raw = _prefs.getString(_keyNotifPrefs);
    if (raw == null || raw.isEmpty) {
      return const NotificationPreferences();
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        return NotificationPreferences.fromJson(decoded);
      }
    } catch (_) {}
    return const NotificationPreferences();
  }

  Future<void> setNotificationPreferences(NotificationPreferences prefs) =>
      _prefs.setString(_keyNotifPrefs, jsonEncode(prefs.toJson()));

  String? get authToken => _cachedAuthToken;
  String? get refreshToken => _cachedRefreshToken;
  String? get sessionId => _cachedSessionId;

  Future<void> setSessionTokens({
    required String? accessToken,
    String? refreshToken,
    String? sessionId,
  }) async {
    _cachedAuthToken = accessToken?.trim().isNotEmpty == true ? accessToken!.trim() : null;
    _cachedRefreshToken = refreshToken?.trim().isNotEmpty == true ? refreshToken!.trim() : null;
    _cachedSessionId = sessionId?.trim().isNotEmpty == true ? sessionId!.trim() : null;
    await _secureStorage.writeTokens(
      accessToken: _cachedAuthToken,
      refreshToken: _cachedRefreshToken,
      sessionId: _cachedSessionId,
    );
    if (_prefs.containsKey(_keyAuthToken)) {
      await _prefs.remove(_keyAuthToken);
    }
  }

  Future<void> setAuthToken(String? token) => setSessionTokens(
        accessToken: token,
        refreshToken: _cachedRefreshToken,
        sessionId: _cachedSessionId,
      );

  Future<void> clearSession() async {
    _cachedAuthToken = null;
    _cachedRefreshToken = null;
    _cachedSessionId = null;
    await _secureStorage.clearAll();
    await _prefs.remove(_keyAuthToken);
    await _prefs.remove(_keyProfileName);
    await _prefs.remove(_keyProfileEmail);
  }
}
