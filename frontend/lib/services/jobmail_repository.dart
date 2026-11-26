import '../models/connected_account.dart';
import '../models/dashboard_stats.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../models/notification_item.dart';
import '../models/notification_preferences.dart';

/// Filter parameters for querying classified job emails.
class EmailFilter {
  const EmailFilter({
    this.query = '',
    this.category,
    this.company,
    this.isRead,
    this.startDate,
    this.endDate,
  });

  final String query;
  final EmailCategory? category;
  final String? company;
  final bool? isRead;
  final DateTime? startDate;
  final DateTime? endDate;

  bool get hasActiveFilters =>
      query.trim().isNotEmpty ||
      category != null ||
      (company != null && company!.trim().isNotEmpty) ||
      isRead != null ||
      startDate != null ||
      endDate != null;

  EmailFilter copyWith({
    String? query,
    EmailCategory? category,
    bool clearCategory = false,
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
      company: clearCompany ? null : (company ?? this.company),
      isRead: clearIsRead ? null : (isRead ?? this.isRead),
      startDate: clearDates ? null : (startDate ?? this.startDate),
      endDate: clearDates ? null : (endDate ?? this.endDate),
    );
  }
}

/// Contract for JobMail data operations across backend API and tests.
abstract class JobMailRepository {
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

  Future<void> triggerSync({String? accountId});

  Future<List<ConnectedAccount>> getConnectedAccounts();

  Future<String> initiateGoogleOAuth();

  Future<void> disconnectAccount(String accountId);

  Future<List<NotificationItem>> getNotifications();

  Future<void> markNotificationRead(String notificationId);

  Future<NotificationPreferences> getNotificationPreferences();

  Future<NotificationPreferences> updateNotificationPreferences(
    NotificationPreferences preferences,
  );
}
