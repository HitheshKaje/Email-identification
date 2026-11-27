import '../models/auth_session.dart';
import '../models/connected_account.dart';
import '../models/dashboard_stats.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../models/notification_item.dart';
import '../models/notification_preferences.dart';
import '../models/security_models.dart';
import '../models/user_profile.dart';

/// Filter parameters for querying classified job emails.
class EmailFilter {
  const EmailFilter({
    this.query = '',
    this.category,
    this.accountId,
    this.company,
    this.isRead,
    this.startDate,
    this.endDate,
  });

  final String query;
  final EmailCategory? category;
  final String? accountId;
  final String? company;
  final bool? isRead;
  final DateTime? startDate;
  final DateTime? endDate;

  bool get hasActiveFilters =>
      query.trim().isNotEmpty ||
      category != null ||
      (accountId != null && accountId!.trim().isNotEmpty) ||
      (company != null && company!.trim().isNotEmpty) ||
      isRead != null ||
      startDate != null ||
      endDate != null;

  EmailFilter copyWith({
    String? query,
    EmailCategory? category,
    bool clearCategory = false,
    String? accountId,
    bool clearAccount = false,
    String? company,
    bool clearCompany = false,
    bool? isRead,
    bool clearIsRead = false,
    DateTime? startDate,
    DateTime? endDate,
    bool clearDates = false,
  }) {
    return EmailFilter(
      query: query ?? this.query,
      category: clearCategory ? null : (category ?? this.category),
      accountId: clearAccount ? null : (accountId ?? this.accountId),
      company: clearCompany ? null : (company ?? this.company),
      isRead: clearIsRead ? null : (isRead ?? this.isRead),
      startDate: clearDates ? null : (startDate ?? this.startDate),
      endDate: clearDates ? null : (endDate ?? this.endDate),
    );
  }
}

/// Contract for JobMail data operations across backend API and tests.
abstract class JobMailRepository {
  Future<AuthSession> register({
    required String name,
    required String email,
    required String password,
  });

  Future<AuthSession> login({
    required String email,
    required String password,
  });

  Future<AuthSession> verifyMfaLogin({
    required String challengeToken,
    required String code,
  });

  Future<AuthSession> refreshSession({String? refreshToken});

  Future<void> logout();

  Future<void> logoutAllDevices();

  Future<UserProfile> getCurrentProfile();

  Future<UserProfile> updateProfileName(String name);

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  });

  Future<void> requestPasswordReset(String email);

  Future<void> confirmPasswordReset({
    required String token,
    required String newPassword,
  });

  Future<void> requestEmailVerification();

  Future<UserProfile> confirmEmailVerification(String token);

  Future<MfaSetupInfo> setupMfa();

  Future<UserProfile> enableMfa(String code);

  Future<UserProfile> disableMfa({
    required String password,
    required String code,
  });

  Future<List<SessionInfo>> getActiveSessions();

  Future<void> revokeSession(String sessionId);

  Future<List<SecurityEventItem>> getSecurityEvents();

  Future<PrivacyOverview> getPrivacyOverview();

  Future<PrivacyOverview> updateDataRetention(int retentionDays);

  Future<Map<String, dynamic>> exportMyData();

  Future<String> deleteGmailData({bool disconnectAccounts = false});

  Future<void> deleteAccount({
    required String password,
    String confirmText = 'DELETE',
  });

  Future<DashboardStats> getDashboardStatistics();

  Future<List<EmailItem>> getRecentEmails({int limit = 10});

  Future<List<EmailItem>> getEmails({EmailFilter filter = const EmailFilter()});

  Future<List<EmailItem>> getEmailsByCategory(EmailCategory category);

  Future<EmailItem> getEmailDetail(String emailId);

  Future<EmailItem> markEmailReadStatus(String emailId, {required bool isRead});

  Future<void> submitClassificationFeedback({
    required String emailId,
    required EmailCategory correctedCategory,
  });

  Future<String> triggerSync({String? accountId});

  Future<List<ConnectedAccount>> getConnectedAccounts();

  Future<ConnectedAccount> verifyAccount(String accountId);

  Future<String> initiateGoogleOAuth();

  Future<void> disconnectAccount(String accountId);

  Future<List<NotificationItem>> getNotifications();

  Future<void> markNotificationRead(String notificationId);

  Future<NotificationPreferences> getNotificationPreferences();

  Future<NotificationPreferences> updateNotificationPreferences(
    NotificationPreferences preferences,
  );
}
