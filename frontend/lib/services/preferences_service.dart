import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/notification_preferences.dart';
import '../utils/api_config.dart';

/// Persists non-sensitive local UI and application preferences via SharedPreferences.
class PreferencesService {
  PreferencesService(this._prefs);

  final SharedPreferences _prefs;

  static const String _keyOnboardingDone = 'jobmail_onboarding_done';
  static const String _keyThemeMode = 'jobmail_theme_mode';
  static const String _keyAutoSync = 'jobmail_auto_sync';
  static const String _keySyncIntervalMins = 'jobmail_sync_interval_mins';
  static const String _keyProfileName = 'jobmail_profile_name';
  static const String _keyProfileEmail = 'jobmail_profile_email';
  static const String _keyApiUrl = 'jobmail_api_url';
  static const String _keyNotifPrefs = 'jobmail_notif_prefs';

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

  String get apiBaseUrl =>
      _prefs.getString(_keyApiUrl) ?? ApiConfig.defaultBaseUrl;

  Future<void> setApiBaseUrl(String url) =>
      _prefs.setString(_keyApiUrl, url.trim());

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

  Future<void> clearSession() async {
    await _prefs.remove(_keyProfileName);
    await _prefs.remove(_keyProfileEmail);
    await _prefs.setBool(_keyOnboardingDone, false);
  }
}
