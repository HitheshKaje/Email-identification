import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_settings_provider.dart';
import '../services/api_exceptions.dart';
import '../theme/app_colors.dart';
import '../utils/api_config.dart';
import '../widgets/jobmail_logo.dart';
import '../widgets/main_navigation_shell.dart';

/// Application authentication screen for JobMail Argon2id sign-in, MFA challenge, and password reset.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();

  bool _isRegisterMode = false;
  bool _obscurePassword = true;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    final settings = context.read<AppSettingsProvider>();
    final ok = _isRegisterMode
        ? await settings.register(
            name: _nameController.text,
            email: _emailController.text,
            password: _passwordController.text,
          )
        : await settings.login(
            email: _emailController.text,
            password: _passwordController.text,
          );

    if (!mounted) return;
    if (!ok && settings.mfaRequired) {
      await _promptMfaVerification(settings);
      return;
    }
    if (!ok) return;

    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => const MainNavigationShell(),
      ),
    );
  }

  Future<void> _promptMfaVerification(AppSettingsProvider settings) async {
    final codeCtrl = TextEditingController();
    final verified = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Two-Factor Authentication'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text(
                'Enter the 6-digit verification code from your authenticator app or a backup recovery code.',
              ),
              const SizedBox(height: 12),
              TextField(
                controller: codeCtrl,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'MFA Code',
                  prefixIcon: Icon(Icons.phonelink_lock_rounded),
                ),
              ),
            ],
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () {
                settings.clearMfaChallenge();
                Navigator.pop(dialogContext, false);
              },
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                final ok = await settings.verifyMfaChallenge(codeCtrl.text);
                if (dialogContext.mounted) {
                  Navigator.pop(dialogContext, ok);
                }
              },
              child: const Text('Verify & Sign In'),
            ),
          ],
        );
      },
    );
    codeCtrl.dispose();

    if (verified == true && mounted) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) => const MainNavigationShell(),
        ),
      );
    }
  }

  Future<void> _showForgotPasswordDialog(AppSettingsProvider settings) async {
    final emailCtrl = TextEditingController(text: _emailController.text);
    final tokenCtrl = TextEditingController();
    final newPassCtrl = TextEditingController();
    bool sent = false;
    bool busy = false;
    String? errorText;

    final completed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (context, setState) {
            return AlertDialog(
              title: const Text('Reset Password'),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    TextField(
                      controller: emailCtrl,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(
                        labelText: 'Account Email',
                      ),
                    ),
                    const SizedBox(height: 10),
                    OutlinedButton(
                      onPressed: busy
                          ? null
                          : () async {
                              setState(() {
                                busy = true;
                                errorText = null;
                              });
                              try {
                                await settings.requestPasswordReset(emailCtrl.text);
                                setState(() {
                                  sent = true;
                                  busy = false;
                                });
                              } catch (e) {
                                setState(() {
                                  busy = false;
                                  errorText = e is ApiException
                                      ? e.message
                                      : 'Unable to send reset request.';
                                });
                              }
                            },
                      child: Text(sent ? 'Reset Requested' : 'Send Reset Token'),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: tokenCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Reset Token',
                      ),
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      controller: newPassCtrl,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: 'New Strong Password',
                      ),
                    ),
                    if (errorText != null) ...<Widget>[
                      const SizedBox(height: 8),
                      Text(
                        errorText!,
                        style: const TextStyle(color: AppColors.error, fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ),
              actions: <Widget>[
                TextButton(
                  onPressed: busy ? null : () => Navigator.pop(dialogContext, false),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: busy
                      ? null
                      : () async {
                          if (tokenCtrl.text.trim().isEmpty ||
                              newPassCtrl.text.isEmpty) {
                            return;
                          }
                          setState(() {
                            busy = true;
                            errorText = null;
                          });
                          try {
                            await settings.confirmPasswordReset(
                              token: tokenCtrl.text,
                              newPassword: newPassCtrl.text,
                            );
                            if (dialogContext.mounted) {
                              Navigator.pop(dialogContext, true);
                            }
                          } catch (e) {
                            setState(() {
                              busy = false;
                              errorText = e is ApiException
                                  ? e.message
                                  : 'Password reset failed.';
                            });
                          }
                        },
                  child: const Text('Reset Password'),
                ),
              ],
            );
          },
        );
      },
    );

    emailCtrl.dispose();
    tokenCtrl.dispose();
    newPassCtrl.dispose();

    if (completed == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Password reset completed. Please sign in.'),
        ),
      );
    }
  }

  Future<void> _editServerUrl(AppSettingsProvider settings) async {
    final controller = TextEditingController(text: settings.apiBaseUrl);
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Backend Server URL'),
          content: TextField(
            controller: controller,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
              labelText: 'API Base URL',
              hintText: ApiConfig.endpointHint,
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Save'),
            ),
          ],
        );
      },
    );
    if (saved == true && mounted) {
      final ok = await settings.updateApiBaseUrl(controller.text);
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              ApiConfig.allowLocalHttpInCurrentBuild
                  ? 'Invalid URL. Use HTTPS or a local LAN/loopback HTTP address.'
                  : 'Invalid URL. Release builds require an HTTPS backend URL.',
            ),
          ),
        );
      }
    }
    controller.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<AppSettingsProvider>();
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final border = isDark ? AppColors.darkBorder : AppColors.lightBorder;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const Center(child: JobMailLogo(size: 64)),
                  const SizedBox(height: 18),
                  Text(
                    'Welcome to JobMail',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Sign in to access your intelligent recruitment inbox.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 24),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: surface,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: border),
                    ),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          SegmentedButton<bool>(
                            segments: const <ButtonSegment<bool>>[
                              ButtonSegment<bool>(
                                value: false,
                                label: Text('Sign In'),
                              ),
                              ButtonSegment<bool>(
                                value: true,
                                label: Text('Create Account'),
                              ),
                            ],
                            selected: <bool>{_isRegisterMode},
                            onSelectionChanged: (selection) {
                              setState(() {
                                _isRegisterMode = selection.first;
                              });
                            },
                          ),
                          const SizedBox(height: 18),
                          if (_isRegisterMode) ...<Widget>[
                            TextFormField(
                              controller: _nameController,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(
                                labelText: 'Full Name',
                                prefixIcon: Icon(Icons.person_outline_rounded),
                              ),
                              validator: (val) {
                                if (!_isRegisterMode) return null;
                                if (val == null || val.trim().length < 2) {
                                  return 'Enter your full name';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 14),
                          ],
                          TextFormField(
                            controller: _emailController,
                            keyboardType: TextInputType.emailAddress,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: 'Email Address',
                              prefixIcon: Icon(Icons.email_outlined),
                            ),
                            validator: (val) {
                              if (val == null || !val.contains('@')) {
                                return 'Enter a valid email address';
                              }
                              return null;
                            },
                          ),
                          const SizedBox(height: 14),
                          TextFormField(
                            controller: _passwordController,
                            obscureText: _obscurePassword,
                            textInputAction: TextInputAction.done,
                            onFieldSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline_rounded),
                              suffixIcon: IconButton(
                                onPressed: () {
                                  setState(() {
                                    _obscurePassword = !_obscurePassword;
                                  });
                                },
                                icon: Icon(
                                  _obscurePassword
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined,
                                ),
                              ),
                            ),
                            validator: (val) {
                              if (val == null || val.length < 8) {
                                return 'Password must be at least 8 characters';
                              }
                              return null;
                            },
                          ),
                          if (!_isRegisterMode)
                            Align(
                              alignment: Alignment.centerRight,
                              child: TextButton(
                                onPressed: () =>
                                    _showForgotPasswordDialog(settings),
                                child: const Text('Forgot password?'),
                              ),
                            ),
                          if (settings.authError != null) ...<Widget>[
                            const SizedBox(height: 10),
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: AppColors.error.withAlpha(22),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: AppColors.error.withAlpha(90),
                                ),
                              ),
                              child: Text(
                                settings.authError!,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(color: AppColors.error),
                              ),
                            ),
                          ],
                          const SizedBox(height: 16),
                          FilledButton(
                            onPressed:
                                settings.isAuthenticating ? null : _submit,
                            child: settings.isAuthenticating
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : Text(
                                    _isRegisterMode
                                        ? 'Create Account'
                                        : 'Sign In',
                                  ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (ApiConfig.canCustomizeApiUrl) ...<Widget>[
                    const SizedBox(height: 14),
                    TextButton.icon(
                      onPressed: () => _editServerUrl(settings),
                      icon: const Icon(Icons.dns_outlined, size: 16),
                      label: Text('Server: ${settings.apiBaseUrl}'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
