import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../providers/emails_provider.dart';
import '../services/api_exceptions.dart';
import '../utils/responsive.dart';
import '../widgets/email_card.dart';
import '../widgets/state_views.dart';
import 'email_detail_screen.dart';

/// Drill-down screen displaying emails belonging to a single recruitment category.
class CategoryEmailsScreen extends StatefulWidget {
  const CategoryEmailsScreen({super.key, required this.category});

  final EmailCategory category;

  @override
  State<CategoryEmailsScreen> createState() => _CategoryEmailsScreenState();
}

class _CategoryEmailsScreenState extends State<CategoryEmailsScreen> {
  List<EmailItem> _items = const <EmailItem>[];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final fetched =
          await context.read<EmailsProvider>().fetchByCategory(widget.category);
      if (!mounted) return;
      setState(() {
        _items = fetched;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to load ${widget.category.displayName}.';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final maxWidth = Responsive.contentMaxWidth(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.category.displayName),
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: RefreshIndicator(
            onRefresh: _load,
            child: _buildBody(context),
          ),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading && _items.isEmpty) {
      return LoadingStateView(
        message: 'Loading ${widget.category.displayName}...',
      );
    }

    if (_errorMessage != null && _items.isEmpty) {
      return ListView(
        children: <Widget>[
          ErrorStateView(
            message: _errorMessage!,
            onRetry: _load,
          ),
        ],
      );
    }

    if (_items.isEmpty) {
      return ListView(
        children: <Widget>[
          EmptyStateView(
            icon: widget.category.icon,
            title: 'No ${widget.category.displayName} yet',
            subtitle: widget.category.description,
            actionLabel: 'Refresh',
            onAction: _load,
          ),
        ],
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      itemCount: _items.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final email = _items[index];
        return EmailCard(
          email: email,
          onTap: () async {
            await Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => EmailDetailScreen(initialEmail: email),
              ),
            );
          },
        );
      },
    );
  }
}
