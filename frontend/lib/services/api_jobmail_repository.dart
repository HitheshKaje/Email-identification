import '../models/auth_session.dart';
import '../models/connected_account.dart';
import '../models/dashboard_stats.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../models/notification_item.dart';
import '../models/notification_preferences.dart';
import '../models/security_models.dart';
import '../models/user_profile.dart';
import 'api_client.dart';
import 'jobmail_repository.dart';

/// Production repository backed by the hardened JobMail FastAPI REST endpoints.
class ApiJobMailRepository implements JobMailRepository {
  ApiJobMailRepository(this._client);

  final ApiClient _client;

  @override
  Future<AuthSession> register({
    required String name,
    required String email,
    required String password,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/register',
      data: <String, dynamic>{
        'name': name.trim(),
        'email': email.trim(),
        'password': password,
      },
    );
    final session = AuthSession.fromJson(response.data ?? <String, dynamic>{});
    if (session.accessToken.isNotEmpty) {
      _client.setAuthToken(session.accessToken);
    }
    return session;
  }

  @override
  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/login',
      data: <String, dynamic>{
        'email': email.trim(),
        'password': password,
      },
    );
    final session = AuthSession.fromJson(response.data ?? <String, dynamic>{});
    if (session.accessToken.isNotEmpty) {
      _client.setAuthToken(session.accessToken);
    }
    return session;
  }

  @override
  Future<AuthSession> verifyMfaLogin({
    required String challengeToken,
    required String code,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/mfa/verify-login',
      data: <String, dynamic>{
        'challenge_token': challengeToken,
        'code': code.trim(),
      },
    );
    final session = AuthSession.fromJson(response.data ?? <String, dynamic>{});
    if (session.accessToken.isNotEmpty) {
      _client.setAuthToken(session.accessToken);
    }
    return session;
  }

  @override
  Future<AuthSession> refreshSession({String? refreshToken}) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/refresh',
      data: refreshToken != null && refreshToken.isNotEmpty
          ? <String, dynamic>{'refresh_token': refreshToken}
          : <String, dynamic>{},
    );
    final session = AuthSession.fromJson(response.data ?? <String, dynamic>{});
    if (session.accessToken.isNotEmpty) {
      _client.setAuthToken(session.accessToken);
    }
    return session;
  }

  @override
  Future<void> logout() async {
    await _client.post<dynamic>('/auth/logout');
    _client.setAuthToken(null);
  }

  @override
  Future<void> logoutAllDevices() async {
    await _client.post<dynamic>('/auth/logout-all');
    _client.setAuthToken(null);
  }

  @override
  Future<UserProfile> getCurrentProfile() async {
    final response = await _client.get<Map<String, dynamic>>('/auth/me');
    return UserProfile.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<UserProfile> updateProfileName(String name) async {
    final response = await _client.patch<Map<String, dynamic>>(
      '/auth/me',
      data: <String, dynamic>{'name': name.trim()},
    );
    return UserProfile.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _client.post<dynamic>(
      '/auth/password/change',
      data: <String, dynamic>{
        'current_password': currentPassword,
        'new_password': newPassword,
      },
    );
  }

  @override
  Future<void> requestPasswordReset(String email) async {
    await _client.post<dynamic>(
      '/auth/password/forgot',
      data: <String, dynamic>{'email': email.trim()},
    );
  }

  @override
  Future<void> confirmPasswordReset({
    required String token,
    required String newPassword,
  }) async {
    await _client.post<dynamic>(
      '/auth/password/reset',
      data: <String, dynamic>{
        'token': token.trim(),
        'new_password': newPassword,
      },
    );
  }

  @override
  Future<void> requestEmailVerification() async {
    await _client.post<dynamic>('/auth/verify-email/request');
  }

  @override
  Future<UserProfile> confirmEmailVerification(String token) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/verify-email/confirm',
      data: <String, dynamic>{'token': token.trim()},
    );
    return UserProfile.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<MfaSetupInfo> setupMfa() async {
    final response = await _client.post<Map<String, dynamic>>('/auth/mfa/setup');
    return MfaSetupInfo.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<UserProfile> enableMfa(String code) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/mfa/enable',
      data: <String, dynamic>{'code': code.trim()},
    );
    return UserProfile.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<UserProfile> disableMfa({
    required String password,
    required String code,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/mfa/disable',
      data: <String, dynamic>{
        'password': password,
        'code': code.trim(),
      },
    );
    return UserProfile.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<List<SessionInfo>> getActiveSessions() async {
    final response = await _client.get<dynamic>('/auth/sessions');
    final items = _extractList(response.data);
    return items
        .whereType<Map<String, dynamic>>()
        .map(SessionInfo.fromJson)
        .toList();
  }

  @override
  Future<void> revokeSession(String sessionId) async {
    await _client.delete<dynamic>('/auth/sessions/$sessionId');
  }

  @override
  Future<List<SecurityEventItem>> getSecurityEvents() async {
    final response = await _client.get<dynamic>('/auth/security-events');
    final items = _extractList(response.data);
    return items
        .whereType<Map<String, dynamic>>()
        .map(SecurityEventItem.fromJson)
        .toList();
  }

  @override
  Future<PrivacyOverview> getPrivacyOverview() async {
    final response = await _client.get<Map<String, dynamic>>('/privacy/overview');
    return PrivacyOverview.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<PrivacyOverview> updateDataRetention(int retentionDays) async {
    final response = await _client.patch<Map<String, dynamic>>(
      '/privacy/retention',
      data: <String, dynamic>{'retention_days': retentionDays},
    );
    return PrivacyOverview.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<Map<String, dynamic>> exportMyData() async {
    final response = await _client.get<Map<String, dynamic>>('/privacy/export');
    return response.data ?? <String, dynamic>{};
  }

  @override
  Future<String> deleteGmailData({bool disconnectAccounts = false}) async {
    final response = await _client.delete<Map<String, dynamic>>(
      '/privacy/gmail-data',
      queryParameters: <String, dynamic>{
        'disconnect_accounts': disconnectAccounts,
      },
    );
    return response.data?['message']?.toString() ?? 'Gmail data deleted.';
  }

  @override
  Future<void> deleteAccount({
    required String password,
    String confirmText = 'DELETE',
  }) async {
    await _client.delete<dynamic>(
      '/privacy/account',
      data: <String, dynamic>{
        'password': password,
        'confirm_text': confirmText,
      },
    );
    _client.setAuthToken(null);
  }

  @override
  Future<DashboardStats> getDashboardStatistics() async {
    final response = await _client.get<Map<String, dynamic>>(
      '/dashboard/statistics',
    );
    return DashboardStats.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<List<EmailItem>> getRecentEmails({int limit = 10}) async {
    final response = await _client.get<dynamic>(
      '/dashboard/recent-emails',
      queryParameters: <String, dynamic>{'limit': limit},
    );
    return _parseEmailList(response.data);
  }

  @override
  Future<List<EmailItem>> getEmails({
    EmailFilter filter = const EmailFilter(),
  }) async {
    final params = <String, dynamic>{};
    if (filter.query.trim().isNotEmpty) {
      params['q'] = filter.query.trim();
    }
    if (filter.category != null) {
      params['category'] = filter.category!.apiValue;
    }
    if (filter.accountId != null && filter.accountId!.trim().isNotEmpty) {
      params['account_id'] = filter.accountId!.trim();
    }
    if (filter.company != null && filter.company!.trim().isNotEmpty) {
      params['company'] = filter.company!.trim();
    }
    if (filter.isRead != null) {
      params['is_read'] = filter.isRead;
    }
    if (filter.startDate != null) {
      params['start_date'] = filter.startDate!.toIso8601String();
    }
    if (filter.endDate != null) {
      params['end_date'] = filter.endDate!.toIso8601String();
    }

    final endpoint = filter.query.trim().isNotEmpty ? '/emails/search' : '/emails';
    final response = await _client.get<dynamic>(
      endpoint,
      queryParameters: params,
    );
    return _parseEmailList(response.data);
  }

  @override
  Future<List<EmailItem>> getEmailsByCategory(EmailCategory category) async {
    final response = await _client.get<dynamic>(
      '/emails/category/${category.apiValue}',
    );
    return _parseEmailList(response.data);
  }

  @override
  Future<EmailItem> getEmailDetail(String emailId) async {
    final response = await _client.get<Map<String, dynamic>>(
      '/emails/$emailId',
    );
    return EmailItem.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<EmailItem> markEmailReadStatus(
    String emailId, {
    required bool isRead,
  }) async {
    final response = await _client.patch<Map<String, dynamic>>(
      '/emails/$emailId',
      data: <String, dynamic>{'is_read': isRead},
    );
    return EmailItem.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<void> submitClassificationFeedback({
    required String emailId,
    required EmailCategory correctedCategory,
  }) async {
    await _client.post<dynamic>(
      '/classification/feedback',
      data: <String, dynamic>{
        'email_id': emailId,
        'corrected_category': correctedCategory.apiValue,
      },
    );
  }

  @override
  Future<String> triggerSync({String? accountId}) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/emails/sync',
      data: accountId != null
          ? <String, dynamic>{'account_id': accountId}
          : <String, dynamic>{},
    );
    return response.data?['message']?.toString() ?? 'Gmail sync complete.';
  }

  @override
  Future<List<ConnectedAccount>> getConnectedAccounts() async {
    final response = await _client.get<dynamic>('/auth/accounts');
    final items = _extractList(response.data);
    return items
        .whereType<Map<String, dynamic>>()
        .map(ConnectedAccount.fromJson)
        .toList();
  }

  @override
  Future<ConnectedAccount> verifyAccount(String accountId) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/accounts/$accountId/verify',
    );
    return ConnectedAccount.fromJson(response.data ?? <String, dynamic>{});
  }

  @override
  Future<String> initiateGoogleOAuth() async {
    final response = await _client.post<Map<String, dynamic>>(
      '/auth/google/connect',
    );
    final url = response.data?['authorization_url']?.toString() ?? '';
    return url;
  }

  @override
  Future<void> disconnectAccount(String accountId) async {
    await _client.delete<dynamic>('/auth/accounts/$accountId');
  }

  @override
  Future<List<NotificationItem>> getNotifications() async {
    final response = await _client.get<dynamic>('/notifications');
    final items = _extractList(response.data);
    return items
        .whereType<Map<String, dynamic>>()
        .map(NotificationItem.fromJson)
        .toList();
  }

  @override
  Future<void> markNotificationRead(String notificationId) async {
    await _client.patch<dynamic>(
      '/notifications/$notificationId',
      data: <String, dynamic>{'is_read': true},
    );
  }

  @override
  Future<NotificationPreferences> getNotificationPreferences() async {
    final response = await _client.get<Map<String, dynamic>>(
      '/notifications/preferences',
    );
    return NotificationPreferences.fromJson(
      response.data ?? <String, dynamic>{},
    );
  }

  @override
  Future<NotificationPreferences> updateNotificationPreferences(
    NotificationPreferences preferences,
  ) async {
    final response = await _client.patch<Map<String, dynamic>>(
      '/notifications/preferences',
      data: preferences.toJson(),
    );
    return NotificationPreferences.fromJson(
      response.data ?? <String, dynamic>{},
    );
  }

  List<EmailItem> _parseEmailList(dynamic data) {
    final items = _extractList(data);
    return items
        .whereType<Map<String, dynamic>>()
        .map(EmailItem.fromJson)
        .toList();
  }

  List<dynamic> _extractList(dynamic data) {
    if (data is List) return data;
    if (data is Map<String, dynamic>) {
      final raw = data['items'] ?? data['emails'] ?? data['results'];
      if (raw is List) return raw;
    }
    return const <dynamic>[];
  }
}
