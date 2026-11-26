import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jobmail/app.dart';
import 'package:jobmail/models/connected_account.dart';
import 'package:jobmail/models/dashboard_stats.dart';
import 'package:jobmail/models/email_category.dart';
import 'package:jobmail/models/email_item.dart';
import 'package:jobmail/models/notification_item.dart';
import 'package:jobmail/models/notification_preferences.dart';
import 'package:jobmail/screens/splash_screen.dart';
import 'package:jobmail/services/jobmail_repository.dart';
import 'package:jobmail/services/preferences_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Test-only in-memory repository so UI behavior can be verified cleanly
/// without placing mock data in production `lib/` code.
class FakeJobMailRepository implements JobMailRepository {
  FakeJobMailRepository() {
    _emails = <EmailItem>[
      EmailItem(
        id: 'email-1',
        accountId: 'acc-1',
        gmailMessageId: '18f0abc123',
        senderName: 'Infosys Talent Acquisition',
        senderEmail: 'careers@infosys.com',
        subject: 'Shortlisted for Software Developer Interview',
        bodyPreview:
            'Congratulations! You have been shortlisted for the Software Developer interview at Infosys.',
        fullContent:
            'Congratulations! You have been shortlisted for the Software Developer interview at Infosys scheduled next Tuesday at 11:00 AM.',
        receivedAt: DateTime(2026, 11, 25, 10, 30),
        category: EmailCategory.interview,
        confidence: 0.96,
        companyName: 'Infosys',
        jobRole: 'Software Developer',
        isRead: false,
      ),
      EmailItem(
        id: 'email-2',
        accountId: 'acc-1',
        gmailMessageId: '18f0abc456',
        senderName: 'Campus Hiring Team',
        senderEmail: 'internships@techcorp.io',
        subject: 'Python Developer Internship Opportunity',
        bodyPreview:
            'We are pleased to announce internship opportunities for Python developers.',
        receivedAt: DateTime(2026, 11, 24, 15, 15),
        category: EmailCategory.internship,
        confidence: 0.93,
        companyName: 'TechCorp',
        jobRole: 'Python Developer Intern',
        isRead: true,
      ),
      EmailItem(
        id: 'email-3',
        accountId: 'acc-1',
        gmailMessageId: '18f0abc789',
        senderName: 'Power Utility Billing',
        senderEmail: 'billing@power.example',
        subject: 'Electricity bill ready',
        bodyPreview: 'Your electricity bill is ready for payment.',
        receivedAt: DateTime(2026, 11, 23, 9, 0),
        category: EmailCategory.other,
        confidence: 0.99,
        isRead: true,
      ),
    ];

    _accounts = <ConnectedAccount>[
      ConnectedAccount(
        id: 'acc-1',
        emailAddress: 'candidate.jobs@gmail.com',
        provider: 'google',
        connectedAt: DateTime(2026, 11, 20),
        lastSyncedAt: DateTime(2026, 11, 26, 12, 0),
        syncStatus: AccountSyncStatus.synced,
      ),
    ];

    _notifications = <NotificationItem>[
      NotificationItem(
        id: 'notif-1',
        emailId: 'email-1',
        title: 'New Interview Invitation!',
        message: 'You have received an interview invitation from Infosys.',
        category: EmailCategory.interview,
        createdAt: DateTime(2026, 11, 25, 10, 31),
        isRead: false,
      ),
    ];
  }

  late List<EmailItem> _emails;
  late List<ConnectedAccount> _accounts;
  late List<NotificationItem> _notifications;
  NotificationPreferences _prefs = const NotificationPreferences();

  @override
  Future<DashboardStats> getDashboardStatistics() async {
    final jobEmails =
        _emails.where((e) => e.category != EmailCategory.other).toList();
    final counts = <EmailCategory, int>{};
    for (final email in jobEmails) {
      counts[email.category] = (counts[email.category] ?? 0) + 1;
    }
    return DashboardStats(
      totalJobEmails: jobEmails.length,
      newOpportunities: (counts[EmailCategory.job] ?? 0) +
          (counts[EmailCategory.internship] ?? 0),
      interviewInvitations: counts[EmailCategory.interview] ?? 0,
      assessmentInvitations: counts[EmailCategory.assessment] ?? 0,
      unreadCount: jobEmails.where((e) => !e.isRead).length,
      categoryCounts: counts,
    );
  }

  @override
  Future<List<EmailItem>> getRecentEmails({int limit = 10}) async {
    return _emails
        .where((e) => e.category != EmailCategory.other)
        .take(limit)
        .toList();
  }

  @override
  Future<List<EmailItem>> getEmails({
    EmailFilter filter = const EmailFilter(),
  }) async {
    return _emails.where((e) {
      if (e.category == EmailCategory.other) return false;
      if (filter.category != null && e.category != filter.category) {
        return false;
      }
      if (filter.isRead != null && e.isRead != filter.isRead) {
        return false;
      }
      if (filter.company != null &&
          filter.company!.isNotEmpty &&
          (e.companyName?.toLowerCase() ?? '') !=
              filter.company!.toLowerCase()) {
        return false;
      }
      if (filter.query.trim().isNotEmpty) {
        final q = filter.query.trim().toLowerCase();
        final haystack =
            '${e.subject} ${e.senderName} ${e.companyName ?? ''} ${e.jobRole ?? ''} ${e.bodyPreview}'
                .toLowerCase();
        if (!haystack.contains(q)) return false;
      }
      return true;
    }).toList();
  }

  @override
  Future<List<EmailItem>> getEmailsByCategory(EmailCategory category) async {
    return _emails.where((e) => e.category == category).toList();
  }

  @override
  Future<EmailItem> getEmailDetail(String emailId) async {
    return _emails.firstWhere((e) => e.id == emailId);
  }

  @override
  Future<EmailItem> markEmailReadStatus(
    String emailId, {
    required bool isRead,
  }) async {
    final idx = _emails.indexWhere((e) => e.id == emailId);
    final updated = _emails[idx].copyWith(isRead: isRead);
    _emails[idx] = updated;
    return updated;
  }

  @override
  Future<void> submitClassificationFeedback({
    required String emailId,
    required EmailCategory correctedCategory,
  }) async {
    final idx = _emails.indexWhere((e) => e.id == emailId);
    if (idx != -1) {
      _emails[idx] = _emails[idx].copyWith(category: correctedCategory);
    }
  }

  @override
  Future<void> triggerSync({String? accountId}) async {}

  @override
  Future<List<ConnectedAccount>> getConnectedAccounts() async => _accounts;

  @override
  Future<String> initiateGoogleOAuth() async =>
      'https://accounts.google.com/o/oauth2/v2/auth';

  @override
  Future<void> disconnectAccount(String accountId) async {
    _accounts = _accounts.where((a) => a.id != accountId).toList();
  }

  @override
  Future<List<NotificationItem>> getNotifications() async => _notifications;

  @override
  Future<void> markNotificationRead(String notificationId) async {
    final idx = _notifications.indexWhere((n) => n.id == notificationId);
    if (idx != -1) {
      _notifications[idx] = _notifications[idx].copyWith(isRead: true);
    }
  }

  @override
  Future<NotificationPreferences> getNotificationPreferences() async => _prefs;

  @override
  Future<NotificationPreferences> updateNotificationPreferences(
    NotificationPreferences preferences,
  ) async {
    _prefs = preferences;
    return _prefs;
  }
}

void main() {
  Future<PreferencesService> buildPrefs({bool onboardingDone = false}) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'jobmail_onboarding_done': onboardingDone,
    });
    final sp = await SharedPreferences.getInstance();
    return PreferencesService(sp);
  }

  testWidgets('Splash navigates to Onboarding and then Dashboard',
      (WidgetTester tester) async {
    final prefs = await buildPrefs(onboardingDone: false);
    final repo = FakeJobMailRepository();

    await tester.pumpWidget(
      JobMailApp(
        repository: repo,
        preferencesService: prefs,
        homeOverride: const SplashScreen(
          splashDuration: Duration(milliseconds: 100),
        ),
      ),
    );

    expect(find.text('JobMail'), findsOneWidget);
    expect(find.text('Never Miss a Job Opportunity.'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 150));
    await tester.pumpAndSettle();

    expect(find.text('Connect your email accounts'), findsOneWidget);
    expect(find.text('Get Started'), findsOneWidget);

    await tester.tap(find.text('Get Started'));
    await tester.pumpAndSettle();

    expect(find.text('Total Job Emails'), findsOneWidget);
    expect(find.text('Shortlisted for Software Developer Interview'),
        findsOneWidget);
  });

  testWidgets('Navigation covers Inbox, Categories, Accounts, Details, Alerts',
      (WidgetTester tester) async {
    final prefs = await buildPrefs(onboardingDone: true);
    final repo = FakeJobMailRepository();

    await tester.pumpWidget(
      JobMailApp(
        repository: repo,
        preferencesService: prefs,
        homeOverride: const SplashScreen(
          splashDuration: Duration(milliseconds: 50),
        ),
      ),
    );

    await tester.pump(const Duration(milliseconds: 80));
    await tester.pumpAndSettle();

    // Open Email Details from Dashboard
    await tester.tap(find.text('Shortlisted for Software Developer Interview'));
    await tester.pumpAndSettle();

    expect(find.text('Email Details'), findsOneWidget);
    expect(find.text('careers@infosys.com'), findsOneWidget);
    expect(find.text('Open in Gmail'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();

    // Switch to Inbox tab (excludes OTHER electricity bill)
    await tester.tap(find.text('Inbox'));
    await tester.pumpAndSettle();
    expect(find.text('Python Developer Internship Opportunity'), findsOneWidget);
    expect(find.text('Electricity bill ready'), findsNothing);

    // Switch to Categories tab
    await tester.tap(find.text('Categories'));
    await tester.pumpAndSettle();
    expect(find.text('Offer Letters'), findsOneWidget);
    expect(find.text('Rejection Notifications'), findsOneWidget);

    // Switch to Accounts tab
    await tester.tap(find.text('Accounts'));
    await tester.pumpAndSettle();
    expect(find.text('candidate.jobs@gmail.com'), findsOneWidget);
    expect(find.text('Connect Gmail'), findsOneWidget);

    // Switch to Settings tab and change Theme
    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('Theme Mode'), findsOneWidget);
    await tester.tap(find.text('Dark'));
    await tester.pumpAndSettle();
  });
}
