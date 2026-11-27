import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_settings_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/jobmail_logo.dart';
import '../widgets/main_navigation_shell.dart';
import 'auth_screen.dart';

class _OnboardingBenefit {
  const _OnboardingBenefit({
    required this.stepNumber,
    required this.title,
    required this.description,
    required this.icon,
    required this.color,
  });

  final int stepNumber;
  final String title;
  final String description;
  final IconData icon;
  final Color color;
}

/// Screen 2: Onboarding explaining JobMail's 4 core career productivity benefits.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  static const List<_OnboardingBenefit> _benefits = <_OnboardingBenefit>[
    _OnboardingBenefit(
      stepNumber: 1,
      title: 'Connect your email accounts',
      description:
          'Link multiple Gmail accounts securely via Google OAuth 2.0 read-only access without ever sharing your password.',
      icon: Icons.mark_email_unread_outlined,
      color: AppColors.primary,
    ),
    _OnboardingBenefit(
      stepNumber: 2,
      title: 'Automatically identify job-related emails',
      description:
          'Smart NLP classification filters out clutter and highlights roles, internships, interviews, assessments, and offers.',
      icon: Icons.auto_awesome_outlined,
      color: AppColors.secondary,
    ),
    _OnboardingBenefit(
      stepNumber: 3,
      title: 'Receive notifications about new opportunities',
      description:
          'Get instant alerts for interview shortlists, online coding assessments, recruitment drives, and offer letters.',
      icon: Icons.notifications_active_outlined,
      color: AppColors.accentPurple,
    ),
    _OnboardingBenefit(
      stepNumber: 4,
      title: 'Manage recruitment emails in one place',
      description:
          'Search by company, category, or date and track every stage of your hiring journey from a single organized inbox.',
      icon: Icons.assignment_turned_in_outlined,
      color: AppColors.accentAmber,
    ),
  ];

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _finishOnboarding() async {
    final settings = context.read<AppSettingsProvider>();
    await settings.completeOnboarding();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => settings.isAuthenticated
            ? const MainNavigationShell()
            : const AuthScreen(),
      ),
    );
  }

  void _nextOrStart() {
    if (_currentPage < _benefits.length - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOutCubic,
      );
    } else {
      _finishOnboarding();
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: Column(
                children: <Widget>[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: <Widget>[
                      const JobMailLogo(size: 36, showWordmark: true),
                      TextButton(
                        onPressed: _finishOnboarding,
                        child: const Text('Skip'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: PageView.builder(
                      controller: _pageController,
                      itemCount: _benefits.length,
                      onPageChanged: (index) {
                        setState(() {
                          _currentPage = index;
                        });
                      },
                      itemBuilder: (context, index) {
                        final item = _benefits[index];
                        return LayoutBuilder(
                          builder: (context, constraints) {
                            return SingleChildScrollView(
                              child: ConstrainedBox(
                                constraints: BoxConstraints(
                                  minHeight: constraints.maxHeight,
                                ),
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: <Widget>[
                                    Container(
                                      width: 112,
                                      height: 112,
                                      decoration: BoxDecoration(
                                        color: item.color.withAlpha(28),
                                        borderRadius:
                                            BorderRadius.circular(32),
                                        border: Border.all(
                                          color: item.color.withAlpha(80),
                                        ),
                                      ),
                                      child: Icon(
                                        item.icon,
                                        size: 54,
                                        color: item.color,
                                      ),
                                    ),
                                    const SizedBox(height: 28),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 12,
                                        vertical: 5,
                                      ),
                                      decoration: BoxDecoration(
                                        color: item.color.withAlpha(24),
                                        borderRadius:
                                            BorderRadius.circular(20),
                                      ),
                                      child: Text(
                                        'Benefit ${item.stepNumber} of ${_benefits.length}',
                                        style: TextStyle(
                                          color: item.color,
                                          fontWeight: FontWeight.w700,
                                          fontSize: 12,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 14),
                                    Text(
                                      item.title,
                                      textAlign: TextAlign.center,
                                      style: Theme.of(context)
                                          .textTheme
                                          .headlineMedium,
                                    ),
                                    const SizedBox(height: 12),
                                    Text(
                                      item.description,
                                      textAlign: TextAlign.center,
                                      style:
                                          Theme.of(context).textTheme.bodyLarge,
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: surface,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: border),
                    ),
                    child: Column(
                      children: _benefits.map((b) {
                        final selected =
                            _benefits.indexOf(b) == _currentPage;
                        return InkWell(
                          onTap: () {
                            _pageController.animateToPage(
                              b.stepNumber - 1,
                              duration: const Duration(milliseconds: 250),
                              curve: Curves.easeOut,
                            );
                          },
                          borderRadius: BorderRadius.circular(10),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 6,
                            ),
                            child: Row(
                              children: <Widget>[
                                Icon(
                                  selected
                                      ? Icons.check_circle_rounded
                                      : Icons.circle_outlined,
                                  size: 18,
                                  color: selected
                                      ? b.color
                                      : Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.color,
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    '${b.stepNumber}. ${b.title}',
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodyMedium
                                        ?.copyWith(
                                          fontWeight: selected
                                              ? FontWeight.w700
                                              : FontWeight.w500,
                                        ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List<Widget>.generate(_benefits.length, (index) {
                      final active = index == _currentPage;
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 220),
                        margin: const EdgeInsets.symmetric(horizontal: 4),
                        width: active ? 24 : 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: active
                              ? Theme.of(context).colorScheme.primary
                              : border,
                          borderRadius: BorderRadius.circular(6),
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: <Widget>[
                      if (_currentPage < _benefits.length - 1) ...<Widget>[
                        Expanded(
                          child: OutlinedButton(
                            onPressed: _nextOrStart,
                            child: const Text('Next'),
                          ),
                        ),
                        const SizedBox(width: 12),
                      ],
                      Expanded(
                        flex: 2,
                        child: FilledButton(
                          onPressed: _finishOnboarding,
                          child: const Text('Get Started'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
