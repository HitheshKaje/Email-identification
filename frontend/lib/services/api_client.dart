import 'package:dio/dio.dart';
import '../utils/api_config.dart';
import 'api_client_web_stub.dart'
    if (dart.library.js_interop) 'api_client_web.dart';
import 'api_exceptions.dart';

/// Centralized Dio HTTP client with HTTPS checks, web cookie CSRF headers, and auto-refresh on 401.
class ApiClient {
  ApiClient({String? baseUrl})
      : _dio = Dio(
          BaseOptions(
            baseUrl: ApiConfig.normalizeUrl(baseUrl ?? ApiConfig.defaultBaseUrl),
            connectTimeout: ApiConfig.connectTimeout,
            receiveTimeout: ApiConfig.receiveTimeout,
            headers: const <String, dynamic>{
              'Content-Type': 'application/json',
              'Accept': 'application/json',
            },
          ),
        ) {
    configureDioForPlatform(_dio);
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final token = _authToken;
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          final csrf = readCsrfCookieToken();
          if (csrf != null && csrf.isNotEmpty) {
            options.headers['X-CSRF-Token'] = csrf;
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          final status = error.response?.statusCode;
          final path = error.requestOptions.path;
          final alreadyRetried =
              error.requestOptions.extra['_retried_refresh'] == true;
          final isAuthAttempt = path.startsWith('/auth/login') ||
              path.startsWith('/auth/register') ||
              path.startsWith('/auth/refresh') ||
              path.startsWith('/auth/mfa/verify-login');

          if (status == 401 &&
              !alreadyRetried &&
              !isAuthAttempt &&
              onRefreshSession != null) {
            try {
              final refreshedToken = await onRefreshSession!();
              if (refreshedToken != null && refreshedToken.isNotEmpty) {
                _authToken = refreshedToken;
                final retryOpts = error.requestOptions;
                retryOpts.extra['_retried_refresh'] = true;
                retryOpts.headers['Authorization'] = 'Bearer $refreshedToken';
                final retried = await _dio.fetch<dynamic>(retryOpts);
                return handler.resolve(retried);
              }
            } catch (_) {}
          }
          handler.next(error);
        },
      ),
    );
  }

  final Dio _dio;
  String? _authToken;
  Future<String?> Function()? onRefreshSession;

  String get baseUrl => _dio.options.baseUrl;

  void updateBaseUrl(String newBaseUrl) {
    final trimmed = newBaseUrl.trim();
    if (trimmed.isNotEmpty && ApiConfig.isValidEndpointUrl(trimmed)) {
      _dio.options.baseUrl = trimmed.endsWith('/')
          ? trimmed.substring(0, trimmed.length - 1)
          : trimmed;
    }
  }

  void setAuthToken(String? token) {
    _authToken = token;
  }

  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      return await _dio.get<T>(path, queryParameters: queryParameters);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      return await _dio.post<T>(
        path,
        data: data,
        queryParameters: queryParameters,
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<Response<T>> patch<T>(
    String path, {
    dynamic data,
  }) async {
    try {
      return await _dio.patch<T>(path, data: data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<Response<T>> delete<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      return await _dio.delete<T>(
        path,
        data: data,
        queryParameters: queryParameters,
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
