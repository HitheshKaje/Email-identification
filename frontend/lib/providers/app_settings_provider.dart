import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../services/preferences_service.dart';

/// Global application settings, theme, profile, and sync configuration state.
class AppSettingsProvider extends ChangeNotifier {
  AppSettingsProvider({
    required PreferencesService preferencesService,
    ApiClient? apiClient,
  })  : _prefs = preferencesService,
        _apiClient = apiClient {
    _onboardingCompleted = _prefs.isOnboardingCompleted;
    _themeMode = _prefs.themeMode;
    _autoSyncEnabled = _prefs.autoSyncEnabled;
    _syncIntervalMinutes = _prefs.syncIntervalMinutes;
    _profileName = _prefs.profileName;
    _profileEmail = _prefs.profileEmail;
    _apiBaseUrl = _prefs.apiBaseUrl;
    _apiClient?.updateBaseUrl(_apiBaseUrl);
  }

  final PreferencesService _prefs;
  final ApiClient? _apiClient;

  late bool _onboardingCompleted;
  late ThemeMode _themeMode;
  late bool _autoSyncEnabled;
  late int _syncIntervalMinutes;
  late String _profileName;
  late String _profileEmail;
  late String _apiBaseUrl;

  bool get isOnboardingCompleted => _onboardingCompleted;
  ThemeMode get themeMode => _themeMode;
  bool get autoSyncEnabled => _autoSyncEnabled;
  int get syncIntervalMinutes => _syncIntervalMinutes;
  String get profileName => _profileName;
  String get profileEmail => _profileEmail;
  String get apiBaseUrl => _apiBaseUrl;

  Future<void> completeOnboarding() async {
    _onboardingCompleted = true;
    await _prefs.setOnboardingCompleted(true);
    notifyListeners();
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    if (_themeMode == mode) return;
    _themeMode = mode;
    await _prefs.setThemeMode(mode);
    notifyListeners();
  }

  Future<void> setAutoSyncEnabled(bool enabled) async {
    _autoSyncEnabled = enabled;
    await _prefs.setAutoSyncEnabled(enabled);
    notifyListeners();
  }

  Future<void> setSyncIntervalMinutes(int minutes) async {
    _syncIntervalMinutes = minutes;
    await _prefs.setSyncIntervalMinutes(minutes);
    notifyListeners();
  }

  Future<void> updateProfile({
    required String name,
    String? email,
  }) async {
    _profileName = name.trim().isEmpty ? 'Candidate' : name.trim();
    await _prefs.setProfileName(_profileName);
    if (email != null) {
      _profileEmail = email.trim();
      await _prefs.setProfileEmail(_profileEmail);
    }
    notifyListeners();
  }

  Future<void> updateApiBaseUrl(String newUrl) async {
    final trimmed = newUrl.trim();
    if (trimmed.isEmpty) return;
    _apiBaseUrl = trimmed;
    _apiClient?.updateBaseUrl(trimmed);
    await _prefs.setApiBaseUrl(trimmed);
    notifyListeners();
  }

  Future<void> logout() async {
    _apiClient?.setAuthToken(null);
    await _prefs.clearSession();
    _profileName = 'Candidate';
    _profileEmail = '';
    _onboardingCompleted = false;
    notifyListeners();
  }
}
