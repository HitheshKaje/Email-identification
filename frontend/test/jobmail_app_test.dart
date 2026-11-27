import 'package:flutter_test/flutter_test.dart';
import 'package:jobmail/app.dart';
import 'package:jobmail/models/auth_session.dart';
import 'package:jobmail/models/connected_account.dart';
import 'package:jobmail/models/dashboard_stats.dart';
import 'package:jobmail/models/email_category.dart';
import 'package:jobmail/models/email_item.dart';
import 'package:jobmail/models/notification_item.dart';
import 'package:jobmail/models/notification_preferences.dart';
import 'package:jobmail/models/security_models.dart';
import 'package:jobmail/models/user_profile.dart';
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
        hasAttachments: true,
        attachmentNames: <String>['interview_schedule.pdf'],
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
  Future<AuthSession> register({
    required String name,
    required String email,
    required String password,
  }) async {
    return AuthSession(
      accessToken: 'test-jwt-token',
      user: UserProfile(id: 'user-1', name: name, email: email),
    );
  }

  @override
  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    return AuthSession(
      accessToken: 'test-jwt-token',
      refreshToken: 'sess-1.refresh-token',
      sessionId: 'sess-1',
      user: UserProfile(
        id: 'user-1',
        name: 'Candidate',
        email: email,
        emailVerified: true,
      ),
    );
  }

  @override
  Future<AuthSession> verifyMfaLogin({
    required String challengeToken,
    required String code,
  }) async =>
      login(email: 'candidate@example.com', password: 'ignored');

  @override
  Future<AuthSession> refreshSession({String? refreshToken}) async =>
      login(email: 'candidate@example.com', password: 'ignored');

  @override
  Future<void> logout() async {}

  @override
  Future<void> logoutAllDevices() async {}

  @override
  Future<UserProfile> getCurrentProfile() async => const UserProfile(
        id: 'user-1',
        name: 'Candidate',
        email: 'candidate@example.com',
        emailVerified: true,
        mfaEnabled: false,
      );

  @override
  Future<UserProfile> updateProfileName(String name) async {
    return UserProfile(
      id: 'user-1',
      name: name,
      email: 'candidate@example.com',
      emailVerified: true,
    );
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {}

  @override
  Future<void> requestPasswordReset(String email) async {}

  @override
  Future<void> confirmPasswordReset({
    required String token,
    required String newPassword,
  }) async {}

  @override
  Future<void> requestEmailVerification() async {}

  @override
  Future<UserProfile> confirmEmailVerification(String token) async =>
      const UserProfile(
        id: 'user-1',
        name: 'Candidate',
        email: 'candidate@example.com',
        emailVerified: true,
      );

  @override
  Future<MfaSetupInfo> setupMfa() async => const MfaSetupInfo(
        secret: 'JBSWY3DPEHPK3PXP',
        provisioningUri: 'otpauth://totp/JobMail:candidate@example.com?secret=JBSWY3DPEHPK3PXP',
        recoveryCodes: <String>['ABCD-1234', 'EFGH-5678'],
      );

  @override
  Future<UserProfile> enableMfa(String code) async => const UserProfile(
        id: 'user-1',
        name: 'Candidate',
        email: 'candidate@example.com',
        emailVerified: true,
        mfaEnabled: true,
      );

  @override
  Future<UserProfile> disableMfa({
    required String password,
    required String code,
  }) async =>
      getCurrentProfile();

  @override
  Future<List<SessionInfo>> getActiveSessions() async => <SessionInfo>[
        SessionInfo(
          id: 'sess-1',
          deviceInfo: 'Flutter Test Client',
          ipAddress: '127.0.0.1',
          createdAt: DateTime(2026, 11, 26),
          lastActiveAt: DateTime(2026, 11, 27),
          expiresAt: DateTime(2026, 12, 10),
          isCurrent: true,
        ),
      ];

  @override
  Future<void> revokeSession(String sessionId) async {}

  @override
  Future<List<SecurityEventItem>> getSecurityEvents() async =>
      <SecurityEventItem>[
        SecurityEventItem(
          id: 'evt-1',
          eventType: 'LOGIN_SUCCESS',
          severity: 'info',
          summary: 'Signed in successfully.',
          createdAt: DateTime(2026, 11, 27),
        ),
      ];

  @override
  Future<PrivacyOverview> getPrivacyOverview() async => PrivacyOverview(
        dataRetentionDays: 180,
        gmailScope: 'https://www.googleapis.com/auth/gmail.readonly',
        emailsStored: _emails.length,
        connectedAccounts: _accounts.length,
        notificationsStored: _notifications.length,
        encryptionAtRest: 'MultiFernet',
        limitedUseNotice: 'Read-only personal job inbox usage only.',
      );

  @override
  Future<PrivacyOverview> updateDataRetention(int retentionDays) async =>
      PrivacyOverview(
        dataRetentionDays: retentionDays,
        gmailScope: 'https://www.googleapis.com/auth/gmail.readonly',
        emailsStored: _emails.length,
        connectedAccounts: _accounts.length,
        notificationsStored: _notifications.length,
        encryptionAtRest: 'MultiFernet',
        limitedUseNotice: 'Read-only personal job inbox usage only.',
      );

  @override
  Future<Map<String, dynamic>> exportMyData() async => <String, dynamic>{
        'emails': _emails.length,
      };

  @override
  Future<String> deleteGmailData({bool disconnectAccounts = false}) async {
    _emails = <EmailItem>[];
    if (disconnectAccounts) _accounts = <ConnectedAccount>[];
    return 'Deleted Gmail data.';
  }

  @override
  Future<void> deleteAccount({
    required String password,
    String confirmText = 'DELETE',
  }) async {}

  @override
  Future<DashboardStats> getDashboardStatistics() async {
    final jobEmails =
        _emails.where((e) => e.category != EmailCategory.other).toList();
    final counts = <EmailCategory, int>{};
    for (final email in jobEmails) {
      counts[email.category] = (counts[email.category] ?? 0) + 1;
    }
    return DashboardStats(
      totalProcessedEmails: _emails.length,
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
      if (filter.accountId != null &&
          filter.accountId!.isNotEmpty &&
          e.accountId != filter.accountId) {
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
  Future<String> triggerSync({String? accountId}) async =>
      'Synced 1 account(s): 2 new email(s), 0 duplicate(s) skipped.';

  @override
  Future<List<ConnectedAccount>> getConnectedAccounts() async => _accounts;

  @override
  Future<ConnectedAccount> verifyAccount(String accountId) async =>
      _accounts.firstWhere((a) => a.id == accountId);

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
  Future<PreferencesService> buildPrefs({
    bool onboardingDone = false,
    bool authenticated = false,
  }) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'jobmail_onboarding_done': onboardingDone,
      if (authenticated) 'jobmail_auth_token': 'test-jwt-token',
    });
    final sp = await SharedPreferences.getInstance();
    return PreferencesService(sp);
  }

  testWidgets('Splash navigates to Onboarding and then AuthScreen',
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

    expect(find.text('Welcome to JobMail'), findsOneWidget);
    expect(find.text('Sign In'), findsWidgets);
  });

  testWidgets('Navigation covers Inbox, Categories, Accounts, Details, Alerts',
      (WidgetTester tester) async {
    final prefs = await buildPrefs(onboardingDone: true, authenticated: true);
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
    expect(find.text('Sanitized Text'), findsOneWidget);
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

    // Switch to Settings tab and verify Security Dashboard sections & Theme
    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('Account Security'), findsOneWidget);
    expect(find.text('Change Password'), findsOneWidget);
    expect(find.text('Active Sessions'), findsOneWidget);
    expect(find.text('Privacy'), findsOneWidget);
    expect(find.text('Theme Mode'), findsOneWidget);
    await tester.tap(find.text('Dark'));
    await tester.pumpAndSettle();
  });
}
