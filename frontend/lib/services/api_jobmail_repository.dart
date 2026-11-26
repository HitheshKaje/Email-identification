import '../models/connected_account.dart';
import '../models/dashboard_stats.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../models/notification_item.dart';
import '../models/notification_preferences.dart';
import 'api_client.dart';
import 'jobmail_repository.dart';

/// Production repository backed by the JobMail FastAPI REST endpoints.
class ApiJobMailRepository implements JobMailRepository {
  ApiJobMailRepository(this._client);

  final ApiClient _client;

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
  Future<void> triggerSync({String? accountId}) async {
    await _client.post<dynamic>(
      '/emails/sync',
      data: accountId != null
          ? <String, dynamic>{'account_id': accountId}
          : <String, dynamic>{},
    );
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
    if (response.data != null && response.data!.isNotEmpty) {
      return NotificationPreferences.fromJson(response.data!);
    }
    return preferences;
  }

  List<EmailItem> _parseEmailList(dynamic raw) {
    final items = _extractList(raw);
    return items
        .whereType<Map<String, dynamic>>()
        .map(EmailItem.fromJson)
        .toList();
  }

  List<dynamic> _extractList(dynamic raw) {
    if (raw is List) return raw;
    if (raw is Map && raw['items'] is List) {
      return raw['items'] as List<dynamic>;
    }
    if (raw is Map && raw['emails'] is List) {
      return raw['emails'] as List<dynamic>;
    }
    if (raw is Map && raw['accounts'] is List) {
      return raw['accounts'] as List<dynamic>;
    }
    if (raw is Map && raw['notifications'] is List) {
      return raw['notifications'] as List<dynamic>;
    }
    return const <dynamic>[];
  }
}
