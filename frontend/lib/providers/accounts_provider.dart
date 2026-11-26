import 'package:flutter/foundation.dart';
import '../models/connected_account.dart';
import '../services/api_exceptions.dart';
import '../services/jobmail_repository.dart';

/// State provider for managing connected Google/Gmail OAuth accounts and syncs.
class AccountsProvider extends ChangeNotifier {
  AccountsProvider(this._repository);

  final JobMailRepository _repository;

  List<ConnectedAccount> _accounts = const <ConnectedAccount>[];
  bool _isLoading = false;
  bool _isConnecting = false;
  String? _syncingAccountId;
  String? _errorMessage;

  List<ConnectedAccount> get accounts => _accounts;
  bool get isLoading => _isLoading;
  bool get isConnecting => _isConnecting;
  String? get syncingAccountId => _syncingAccountId;
  String? get errorMessage => _errorMessage;

  Future<void> loadAccounts() async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      _accounts = await _repository.getConnectedAccounts();
    } on ApiException catch (e) {
      _errorMessage = e.message;
    } catch (_) {
      _errorMessage = 'Unable to load connected Gmail accounts.';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<String?> requestGoogleConnectUrl() async {
    _isConnecting = true;
    _errorMessage = null;
    notifyListeners();

    try {
      return await _repository.initiateGoogleOAuth();
    } on ApiException catch (e) {
      _errorMessage = e.message;
      return null;
    } catch (_) {
      _errorMessage = 'Unable to start Google OAuth connection.';
      return null;
    } finally {
      _isConnecting = false;
      notifyListeners();
    }
  }

  Future<bool> syncAccount(String accountId) async {
    _syncingAccountId = accountId;
    _errorMessage = null;
    notifyListeners();

    try {
      await _repository.triggerSync(accountId: accountId);
      await loadAccounts();
      return true;
    } on ApiException catch (e) {
      _errorMessage = e.message;
      return false;
    } catch (_) {
      _errorMessage = 'Failed to synchronize account.';
      return false;
    } finally {
      _syncingAccountId = null;
      notifyListeners();
    }
  }

  Future<bool> disconnectAccount(String accountId) async {
    _errorMessage = null;
    try {
      await _repository.disconnectAccount(accountId);
      _accounts = _accounts.where((a) => a.id != accountId).toList();
      notifyListeners();
      return true;
    } on ApiException catch (e) {
      _errorMessage = e.message;
      notifyListeners();
      return false;
    } catch (_) {
      _errorMessage = 'Failed to disconnect Gmail account.';
      notifyListeners();
      return false;
    }
  }
}
