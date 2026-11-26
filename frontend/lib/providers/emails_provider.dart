import 'package:flutter/foundation.dart';
import '../models/email_category.dart';
import '../models/email_item.dart';
import '../services/api_exceptions.dart';
import '../services/jobmail_repository.dart';

/// State provider for Job Inbox, search, category drill-down, and email actions.
class EmailsProvider extends ChangeNotifier {
  EmailsProvider(this._repository);

  final JobMailRepository _repository;

  List<EmailItem> _emails = const <EmailItem>[];
  EmailFilter _filter = const EmailFilter();
  bool _isLoading = false;
  String? _errorMessage;

  List<EmailItem> get emails => _emails;
  EmailFilter get filter => _filter;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;

  /// Distinct identified companies available for filtering in the Job Inbox.
  List<String> get availableCompanies {
    final companies = _emails
        .map((e) => e.companyName?.trim())
        .whereType<String>()
        .where((c) => c.isNotEmpty)
        .toSet()
        .toList()
      ..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
    return companies;
  }

  Future<void> loadEmails({EmailFilter? overrideFilter}) async {
    if (overrideFilter != null) {
      _filter = overrideFilter;
    }
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final fetched = await _repository.getEmails(filter: _filter);
      _emails = fetched
          .where((e) => e.category != EmailCategory.other)
          .toList();
    } on ApiException catch (e) {
      _errorMessage = e.message;
    } catch (_) {
      _errorMessage = 'Unable to load job emails.';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateSearchQuery(String query) async {
    _filter = _filter.copyWith(query: query);
    await loadEmails();
  }

  Future<void> setCategoryFilter(EmailCategory? category) async {
    _filter = category == null
        ? _filter.copyWith(clearCategory: true)
        : _filter.copyWith(category: category);
    await loadEmails();
  }

  Future<void> setCompanyFilter(String? company) async {
    _filter = (company == null || company.trim().isEmpty)
        ? _filter.copyWith(clearCompany: true)
        : _filter.copyWith(company: company);
    await loadEmails();
  }

  Future<void> setReadFilter(bool? isRead) async {
    _filter = isRead == null
        ? _filter.copyWith(clearIsRead: true)
        : _filter.copyWith(isRead: isRead);
    await loadEmails();
  }

  Future<void> setDateRangeFilter(DateTime? start, DateTime? end) async {
    _filter = (start == null && end == null)
        ? _filter.copyWith(clearDates: true)
        : _filter.copyWith(startDate: start, endDate: end);
    await loadEmails();
  }

  Future<void> clearFilters() async {
    _filter = const EmailFilter();
    await loadEmails();
  }

  Future<List<EmailItem>> fetchByCategory(EmailCategory category) async {
    return _repository.getEmailsByCategory(category);
  }

  Future<EmailItem> fetchEmailDetail(String emailId) async {
    return _repository.getEmailDetail(emailId);
  }

  Future<EmailItem> toggleReadStatus(
    EmailItem email, {
    required bool isRead,
  }) async {
    final updated = await _repository.markEmailReadStatus(
      email.id,
      isRead: isRead,
    );
    _replaceEmailInList(updated);
    return updated;
  }

  Future<EmailItem> correctCategory(
    EmailItem email,
    EmailCategory newCategory,
  ) async {
    await _repository.submitClassificationFeedback(
      emailId: email.id,
      correctedCategory: newCategory,
    );
    final updated = email.copyWith(category: newCategory, confidence: 1.0);
    _replaceEmailInList(updated);
    return updated;
  }

  void _replaceEmailInList(EmailItem updated) {
    final idx = _emails.indexWhere((e) => e.id == updated.id);
    if (idx != -1) {
      final copy = List<EmailItem>.from(_emails);
      copy[idx] = updated;
      _emails = copy;
      notifyListeners();
    }
  }
}
