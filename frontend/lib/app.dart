import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:provider/single_child_widget.dart';
import 'providers/accounts_provider.dart';
import 'providers/app_settings_provider.dart';
import 'providers/dashboard_provider.dart';
import 'providers/emails_provider.dart';
import 'providers/notifications_provider.dart';
import 'screens/splash_screen.dart';
import 'services/api_client.dart';
import 'services/jobmail_repository.dart';
import 'services/preferences_service.dart';
import 'theme/app_theme.dart';

/// Root JobMail application configuring dependency injection, themes, and routing.
class JobMailApp extends StatelessWidget {
  const JobMailApp({
    super.key,
    required this.repository,
    required this.preferencesService,
    this.apiClient,
    this.homeOverride,
  });

  final JobMailRepository repository;
  final PreferencesService preferencesService;
  final ApiClient? apiClient;
  final Widget? homeOverride;

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: <SingleChildWidget>[
        ChangeNotifierProvider<AppSettingsProvider>(
          create: (_) => AppSettingsProvider(
            preferencesService: preferencesService,
            repository: repository,
            apiClient: apiClient,
          ),
        ),
        ChangeNotifierProvider<DashboardProvider>(
          create: (_) => DashboardProvider(repository),
        ),
        ChangeNotifierProvider<EmailsProvider>(
          create: (_) => EmailsProvider(repository),
        ),
        ChangeNotifierProvider<AccountsProvider>(
          create: (_) => AccountsProvider(repository),
        ),
        ChangeNotifierProvider<NotificationsProvider>(
          create: (_) => NotificationsProvider(repository, preferencesService),
        ),
      ],
      child: Consumer<AppSettingsProvider>(
        builder: (context, settings, _) {
          return MaterialApp(
            title: 'JobMail',
            debugShowCheckedModeBanner: false,
            theme: AppTheme.light(),
            darkTheme: AppTheme.dark(),
            themeMode: settings.themeMode,
            home: homeOverride ?? const SplashScreen(),
          );
        },
      ),
    );
  }
}
