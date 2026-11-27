import 'email_category.dart';

/// Aggregated recruitment email counts displayed on Dashboard and Categories screens.
class DashboardStats {
  const DashboardStats({
    this.totalProcessedEmails = 0,
    this.totalJobEmails = 0,
    this.newOpportunities = 0,
    this.interviewInvitations = 0,
    this.assessmentInvitations = 0,
    this.unreadCount = 0,
    this.categoryCounts = const <EmailCategory, int>{},
  });

  final int totalProcessedEmails;
  final int totalJobEmails;
  final int newOpportunities;
  final int interviewInvitations;
  final int assessmentInvitations;
  final int unreadCount;
  final Map<EmailCategory, int> categoryCounts;

  int countForCategory(EmailCategory category) => categoryCounts[category] ?? 0;

  factory DashboardStats.fromJson(Map<String, dynamic> json) {
    final rawCategories = json['category_counts'];
    final parsedCounts = <EmailCategory, int>{};
    if (rawCategories is Map) {
      rawCategories.forEach((key, value) {
        final category = EmailCategory.fromApi(key?.toString());
        if (value is num) {
          parsedCounts[category] = value.toInt();
        }
      });
    }

    return DashboardStats(
      totalProcessedEmails: _readInt(json['total_processed_emails']),
      totalJobEmails: _readInt(json['total_job_emails']),
      newOpportunities: _readInt(json['new_opportunities']),
      interviewInvitations: _readInt(json['interview_invitations']),
      assessmentInvitations: _readInt(json['assessment_invitations']),
      unreadCount: _readInt(json['unread_count']),
      categoryCounts: parsedCounts,
    );
  }

  static int _readInt(dynamic value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}
