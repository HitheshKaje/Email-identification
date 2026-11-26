import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../providers/emails_provider.dart';
import '../utils/date_formatter.dart';
import '../utils/responsive.dart';
import '../widgets/email_card.dart';
import '../widgets/state_views.dart';
import 'email_detail_screen.dart';

/// Screen 4: Searchable and filterable Job Inbox for classified recruitment emails.
class JobInboxScreen extends StatefulWidget {
  const JobInboxScreen({super.key});

  @override
  State<JobInboxScreen> createState() => _JobInboxScreenState();
}

class _JobInboxScreenState extends State<JobInboxScreen> {
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<EmailsProvider>().loadEmails();
    });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    setState(() {});
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      context.read<EmailsProvider>().updateSearchQuery(value);
    });
  }

  Future<void> _openEmail(EmailItem email) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => EmailDetailScreen(initialEmail: email),
      ),
    );
  }

  Future<void> _pickCompanyFilter(EmailsProvider provider) async {
    final companies = provider.availableCompanies;
    final controller = TextEditingController(
      text: provider.filter.company ?? '',
    );

    final selected = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.fromLTRB(
            20,
            8,
            20,
            MediaQuery.viewInsetsOf(sheetContext).bottom + 24,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                'Filter by Company',
                style: Theme.of(sheetContext).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                decoration: const InputDecoration(
                  hintText: 'Enter company name (e.g., Infosys)',
                  prefixIcon: Icon(Icons.business_outlined),
                ),
                onSubmitted: (val) => Navigator.pop(sheetContext, val),
              ),
              if (companies.isNotEmpty) ...<Widget>[
                const SizedBox(height: 14),
                Text(
                  'Detected Companies',
                  style: Theme.of(sheetContext).textTheme.labelLarge,
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: companies
                      .map(
                        (company) => ActionChip(
                          label: Text(company),
                          onPressed: () => Navigator.pop(sheetContext, company),
                        ),
                      )
                      .toList(),
                ),
              ],
              const SizedBox(height: 18),
              Row(
                children: <Widget>[
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(sheetContext, ''),
                      child: const Text('Clear'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: () =>
                          Navigator.pop(sheetContext, controller.text),
                      child: const Text('Apply'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );

    controller.dispose();
    if (selected != null && mounted) {
      await provider.setCompanyFilter(selected);
    }
  }

  Future<void> _pickDateFilter(EmailsProvider provider) async {
    final choice = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              ListTile(
                leading: const Icon(Icons.all_inclusive_rounded),
                title: const Text('All Dates'),
                onTap: () => Navigator.pop(sheetContext, 'all'),
              ),
              ListTile(
                leading: const Icon(Icons.today_rounded),
                title: const Text('Today'),
                onTap: () => Navigator.pop(sheetContext, 'today'),
              ),
              ListTile(
                leading: const Icon(Icons.date_range_rounded),
                title: const Text('Last 7 Days'),
                onTap: () => Navigator.pop(sheetContext, '7d'),
              ),
              ListTile(
                leading: const Icon(Icons.calendar_month_rounded),
                title: const Text('Last 30 Days'),
                onTap: () => Navigator.pop(sheetContext, '30d'),
              ),
              ListTile(
                leading: const Icon(Icons.edit_calendar_outlined),
                title: const Text('Custom Date Range...'),
                onTap: () => Navigator.pop(sheetContext, 'custom'),
              ),
            ],
          ),
        );
      },
    );

    if (!mounted || choice == null) return;
    final now = DateTime.now();

    if (choice == 'all') {
      await provider.setDateRangeFilter(null, null);
    } else if (choice == 'today') {
      final start = DateTime(now.year, now.month, now.day);
      await provider.setDateRangeFilter(start, now);
    } else if (choice == '7d') {
      await provider.setDateRangeFilter(
        now.subtract(const Duration(days: 7)),
        now,
      );
    } else if (choice == '30d') {
      await provider.setDateRangeFilter(
        now.subtract(const Duration(days: 30)),
        now,
      );
    } else if (choice == 'custom') {
      final picked = await showDateRangePicker(
        context: context,
        firstDate: DateTime(2020),
        lastDate: now.add(const Duration(days: 1)),
      );
      if (picked != null && mounted) {
        await provider.setDateRangeFilter(
          picked.start,
          DateTime(picked.end.year, picked.end.month, picked.end.day, 23, 59),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<EmailsProvider>();
    final filter = provider.filter;
    final maxWidth = Responsive.contentMaxWidth(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Job Inbox'),
        actions: <Widget>[
          if (filter.hasActiveFilters)
            TextButton(
              onPressed: () {
                _searchController.clear();
                provider.clearFilters();
              },
              child: const Text('Reset'),
            ),
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
                child: TextField(
                  controller: _searchController,
                  onChanged: _onSearchChanged,
                  decoration: InputDecoration(
                    hintText: 'Search role, company, sender, or keyword...',
                    prefixIcon: const Icon(Icons.search_rounded),
                    suffixIcon: _searchController.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.close_rounded),
                            onPressed: () {
                              _searchController.clear();
                              provider.updateSearchQuery('');
                              setState(() {});
                            },
                          )
                        : null,
                  ),
                ),
              ),
              SizedBox(
                height: 42,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  children: <Widget>[
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text(
                          filter.isRead == null
                              ? 'All Status'
                              : (filter.isRead! ? 'Read' : 'Unread'),
                        ),
                        selected: filter.isRead != null,
                        onSelected: (_) {
                          final next = filter.isRead == null
                              ? false
                              : (filter.isRead == false ? true : null);
                          provider.setReadFilter(next);
                        },
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        avatar: const Icon(Icons.business_outlined, size: 16),
                        label: Text(
                          filter.company?.isNotEmpty == true
                              ? filter.company!
                              : 'Company',
                        ),
                        selected: filter.company?.isNotEmpty == true,
                        onSelected: (_) => _pickCompanyFilter(provider),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        avatar:
                            const Icon(Icons.calendar_today_outlined, size: 15),
                        label: Text(
                          filter.startDate != null
                              ? DateFormatter.formatShortDateTime(
                                  filter.startDate!,
                                ).split(',').first
                              : 'Date',
                        ),
                        selected: filter.startDate != null,
                        onSelected: (_) => _pickDateFilter(provider),
                      ),
                    ),
                    ...EmailCategory.jobCategories.map((category) {
                      final selected = filter.category == category;
                      return Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: FilterChip(
                          label: Text(category.shortLabel),
                          selected: selected,
                          onSelected: (value) {
                            provider.setCategoryFilter(value ? category : null);
                          },
                        ),
                      );
                    }),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () => provider.loadEmails(),
                  child: _buildEmailList(context, provider),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmailList(BuildContext context, EmailsProvider provider) {
    if (provider.isLoading && provider.emails.isEmpty) {
      return const LoadingStateView(message: 'Loading classified job emails...');
    }

    if (provider.errorMessage != null && provider.emails.isEmpty) {
      return ListView(
        children: <Widget>[
          ErrorStateView(
            message: provider.errorMessage!,
            onRetry: provider.loadEmails,
          ),
        ],
      );
    }

    if (provider.emails.isEmpty) {
      return ListView(
        children: <Widget>[
          EmptyStateView(
            icon: Icons.inbox_outlined,
            title: provider.filter.hasActiveFilters
                ? 'No matching job emails'
                : 'Your Job Inbox is empty',
            subtitle: provider.filter.hasActiveFilters
                ? 'Try clearing or adjusting your search query and active filters.'
                : 'Classified career opportunities from your connected Gmail accounts will appear here.',
            actionLabel:
                provider.filter.hasActiveFilters ? 'Clear Filters' : 'Refresh',
            onAction: provider.filter.hasActiveFilters
                ? () {
                    _searchController.clear();
                    provider.clearFilters();
                  }
                : provider.loadEmails,
          ),
        ],
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 24),
      itemCount: provider.emails.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final email = provider.emails[index];
        return EmailCard(
          email: email,
          onTap: () => _openEmail(email),
        );
      },
    );
  }
}
