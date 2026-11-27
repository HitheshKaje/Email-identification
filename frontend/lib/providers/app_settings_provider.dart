import 'package:flutter/material.dart';
import '../models/auth_session.dart';
import '../models/security_models.dart';
import '../models/user_profile.dart';
import '../services/api_client.dart';
import '../services/api_exceptions.dart';
import '../services/jobmail_repository.dart';
import '../services/preferences_service.dart';
import '../utils/api_config.dart';

/// Global application settings, rotating session auth, security dashboard state, and theme.
class AppSettingsProvider extends ChangeNotifier {
  AppSettingsProvider({
    required PreferencesService preferencesService,
    JobMailRepository? repository,
    ApiClient? apiClient,
  })  : _prefs = preferencesService,
        _repository = repository,
        _apiClient = apiClient {
    _onboardingCompleted = _prefs.isOnboardingCompleted;
    _themeMode = _prefs.themeMode;
    _autoSyncEnabled = _prefs.autoSyncEnabled;
    _syncIntervalMinutes = _prefs.syncIntervalMinutes;
    _profileName = _prefs.profileName;
    _profileEmail = _prefs.profileEmail;
    _apiBaseUrl = _prefs.apiBaseUrl;
    _authToken = _prefs.authToken;
    _refreshToken = _prefs.refreshToken;
    _sessionId = _prefs.sessionId;
    _apiClient?.updateBaseUrl(_apiBaseUrl);
    _apiClient?.setAuthToken(_authToken);
    _apiClient?.onRefreshSession = _handleAutoRefresh;
  }

  final PreferencesService _prefs;
  final JobMailRepository? _repository;
  final ApiClient? _apiClient;

  late bool _onboardingCompleted;
  late ThemeMode _themeMode;
  late bool _autoSyncEnabled;
  late int _syncIntervalMinutes;
  late String _profileName;
  late String _profileEmail;
  late String _apiBaseUrl;
  String? _authToken;
  String? _refreshToken;
  String? _sessionId;
  UserProfile? _currentUser;
  bool _isAuthenticating = false;
  bool _mfaRequired = false;
  String? _mfaChallengeToken;
  String? _authError;

  bool get isOnboardingCompleted => _onboardingCompleted;
  bool get isAuthenticated => _authToken != null && _authToken!.isNotEmpty;
  bool get isAuthenticating => _isAuthenticating;
  bool get mfaRequired => _mfaRequired;
  String? get mfaChallengeToken => _mfaChallengeToken;
  String? get authError => _authError;
  ThemeMode get themeMode => _themeMode;
  bool get autoSyncEnabled => _autoSyncEnabled;
  int get syncIntervalMinutes => _syncIntervalMinutes;
  String get profileName => _currentUser?.name ?? _profileName;
  String get profileEmail => _currentUser?.email ?? _profileEmail;
  UserProfile? get currentUser => _currentUser;
  String get apiBaseUrl => _apiBaseUrl;

  Future<String?> _handleAutoRefresh() async {
    final repo = _repository;
    if (repo == null) return null;
    try {
      final session = await repo.refreshSession(refreshToken: _refreshToken);
      if (session.accessToken.isEmpty) return null;
      await _applySession(session);
      notifyListeners();
      return session.accessToken;
    } catch (_) {
      return null;
    }
  }

  Future<void> completeOnboarding() async {
    _onboardingCompleted = true;
    await _prefs.setOnboardingCompleted(true);
    notifyListeners();
  }

  void clearMfaChallenge() {
    _mfaRequired = false;
    _mfaChallengeToken = null;
    _authError = null;
    notifyListeners();
  }

  Future<bool> register({
    required String name,
    required String email,
    required String password,
  }) async {
    final repo = _repository;
    if (repo == null) return false;
    _isAuthenticating = true;
    _authError = null;
    _mfaRequired = false;
    _mfaChallengeToken = null;
    notifyListeners();

    try {
      final session = await repo.register(
        name: name,
        email: email,
        password: password,
      );
      await _applySession(session);
      return true;
    } on ApiException catch (e) {
      _authError = e.message;
      return false;
    } catch (_) {
      _authError = 'Unable to create account right now.';
      return false;
    } finally {
      _isAuthenticating = false;
      notifyListeners();
    }
  }

  Future<bool> login({
    required String email,
    required String password,
  }) async {
    final repo = _repository;
    if (repo == null) return false;
    _isAuthenticating = true;
    _authError = null;
    _mfaRequired = false;
    _mfaChallengeToken = null;
    notifyListeners();

    try {
      final session = await repo.login(
        email: email,
        password: password,
      );
      if (session.mfaRequired &&
          session.mfaChallengeToken != null &&
          session.mfaChallengeToken!.isNotEmpty) {
        _mfaRequired = true;
        _mfaChallengeToken = session.mfaChallengeToken;
        return false;
      }
      await _applySession(session);
      return true;
    } on ApiException catch (e) {
      _authError = e.message;
      return false;
    } catch (_) {
      _authError = 'Unable to sign in right now.';
      return false;
    } finally {
      _isAuthenticating = false;
      notifyListeners();
    }
  }

  Future<bool> verifyMfaChallenge(String code) async {
    final repo = _repository;
    final challenge = _mfaChallengeToken;
    if (repo == null || challenge == null || challenge.isEmpty) return false;

    _isAuthenticating = true;
    _authError = null;
    notifyListeners();

    try {
      final session = await repo.verifyMfaLogin(
        challengeToken: challenge,
        code: code,
      );
      _mfaRequired = false;
      _mfaChallengeToken = null;
      await _applySession(session);
      return true;
    } on ApiException catch (e) {
      _authError = e.message;
      return false;
    } catch (_) {
      _authError = 'Unable to verify MFA code.';
      return false;
    } finally {
      _isAuthenticating = false;
      notifyListeners();
    }
  }

  Future<void> _applySession(AuthSession session) async {
    _authToken = session.accessToken;
    _refreshToken = session.refreshToken ?? _refreshToken;
    _sessionId = session.sessionId ?? _sessionId;
    _currentUser = session.user;
    _profileName =
        session.user.name.trim().isEmpty ? 'Candidate' : session.user.name.trim();
    _profileEmail = session.user.email.trim();
    _apiClient?.setAuthToken(_authToken);
    await _prefs.setSessionTokens(
      accessToken: _authToken,
      refreshToken: _refreshToken,
      sessionId: _sessionId,
    );
    await _prefs.setProfileName(_profileName);
    await _prefs.setProfileEmail(_profileEmail);
  }

  Future<UserProfile?> refreshProfile() async {
    final repo = _repository;
    if (repo == null || !isAuthenticated) return _currentUser;
    try {
      final profile = await repo.getCurrentProfile();
      _currentUser = profile;
      _profileName = profile.name.trim().isEmpty ? 'Candidate' : profile.name;
      _profileEmail = profile.email.trim();
      await _prefs.setProfileName(_profileName);
      await _prefs.setProfileEmail(_profileEmail);
      notifyListeners();
      return profile;
    } catch (_) {
      return _currentUser;
    }
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

  Future<void> updateProfile({required String name}) async {
    final cleanName = name.trim().isEmpty ? 'Candidate' : name.trim();
    if (isAuthenticated && _repository != null) {
      try {
        final updated = await _repository.updateProfileName(cleanName);
        _currentUser = updated;
        _profileName = updated.name;
      } catch (_) {
        _profileName = cleanName;
      }
    } else {
      _profileName = cleanName;
    }
    await _prefs.setProfileName(_profileName);
    notifyListeners();
  }

  Future<bool> updateApiBaseUrl(String newUrl) async {
    final trimmed = newUrl.trim();
    if (trimmed.isEmpty || !ApiConfig.isValidEndpointUrl(trimmed)) {
      return false;
    }
    _apiBaseUrl = trimmed;
    _apiClient?.updateBaseUrl(trimmed);
    await _prefs.setApiBaseUrl(trimmed);
    notifyListeners();
    return true;
  }

  Future<void> requestPasswordReset(String email) async {
    final repo = _repository;
    if (repo == null) return;
    await repo.requestPasswordReset(email);
  }

  Future<void> confirmPasswordReset({
    required String token,
    required String newPassword,
  }) async {
    final repo = _repository;
    if (repo == null) return;
    await repo.confirmPasswordReset(token: token, newPassword: newPassword);
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final repo = _repository;
    if (repo == null) return;
    await repo.changePassword(
      currentPassword: currentPassword,
      newPassword: newPassword,
    );
  }

  Future<void> requestEmailVerification() async {
    final repo = _repository;
    if (repo == null) return;
    await repo.requestEmailVerification();
  }

  Future<UserProfile?> confirmEmailVerification(String token) async {
    final repo = _repository;
    if (repo == null) return null;
    final updated = await repo.confirmEmailVerification(token);
    _currentUser = updated;
    notifyListeners();
    return updated;
  }

  Future<MfaSetupInfo?> setupMfa() async {
    final repo = _repository;
    if (repo == null) return null;
    return repo.setupMfa();
  }

  Future<UserProfile?> enableMfa(String code) async {
    final repo = _repository;
    if (repo == null) return null;
    final updated = await repo.enableMfa(code);
    _currentUser = updated;
    notifyListeners();
    return updated;
  }

  Future<UserProfile?> disableMfa({
    required String password,
    required String code,
  }) async {
    final repo = _repository;
    if (repo == null) return null;
    final updated = await repo.disableMfa(password: password, code: code);
    _currentUser = updated;
    notifyListeners();
    return updated;
  }

  Future<List<SessionInfo>> getActiveSessions() async {
    final repo = _repository;
    if (repo == null) return const <SessionInfo>[];
    return repo.getActiveSessions();
  }

  Future<void> revokeSession(String sessionId) async {
    final repo = _repository;
    if (repo == null) return;
    await repo.revokeSession(sessionId);
  }

  Future<List<SecurityEventItem>> getSecurityEvents() async {
    final repo = _repository;
    if (repo == null) return const <SecurityEventItem>[];
    return repo.getSecurityEvents();
  }

  Future<PrivacyOverview?> getPrivacyOverview() async {
    final repo = _repository;
    if (repo == null) return null;
    return repo.getPrivacyOverview();
  }

  Future<PrivacyOverview?> updateDataRetention(int days) async {
    final repo = _repository;
    if (repo == null) return null;
    final updated = await repo.updateDataRetention(days);
    _currentUser = _currentUser?.copyWith(dataRetentionDays: updated.dataRetentionDays);
    notifyListeners();
    return updated;
  }

  Future<Map<String, dynamic>> exportMyData() async {
    final repo = _repository;
    if (repo == null) return const <String, dynamic>{};
    return repo.exportMyData();
  }

  Future<String> deleteGmailData({bool disconnectAccounts = false}) async {
    final repo = _repository;
    if (repo == null) return '';
    return repo.deleteGmailData(disconnectAccounts: disconnectAccounts);
  }

  Future<void> deleteAccount({required String password}) async {
    final repo = _repository;
    if (repo != null) {
      await repo.deleteAccount(password: password, confirmText: 'DELETE');
    }
    await _clearLocalSessionState();
  }

  Future<void> logoutAllDevices() async {
    final repo = _repository;
    if (repo != null && isAuthenticated) {
      try {
        await repo.logoutAllDevices();
      } catch (_) {}
    }
    await _clearLocalSessionState();
  }

  Future<void> logout() async {
    final repo = _repository;
    if (repo != null && isAuthenticated) {
      try {
        await repo.logout();
      } catch (_) {}
    }
    await _clearLocalSessionState();
  }

  Future<void> _clearLocalSessionState() async {
    _authToken = null;
    _refreshToken = null;
    _sessionId = null;
    _currentUser = null;
    _mfaRequired = false;
    _mfaChallengeToken = null;
    _authError = null;
    _apiClient?.setAuthToken(null);
    await _prefs.clearSession();
    _profileName = 'Candidate';
    _profileEmail = '';
    notifyListeners();
  }
}
