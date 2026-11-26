import 'package:dio/dio.dart';

/// User-friendly domain exception mapped from HTTP/network errors.
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.isOffline = false});

  final String message;
  final int? statusCode;
  final bool isOffline;

  @override
  String toString() => message;

  factory ApiException.fromDio(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const ApiException(
          'Request timed out while contacting the JobMail server.',
          isOffline: true,
        );
      case DioExceptionType.connectionError:
        return const ApiException(
          'Unable to connect to the JobMail backend server. Ensure the API server is running and reachable.',
          isOffline: true,
        );
      case DioExceptionType.badCertificate:
        return const ApiException(
          'Secure connection failed due to an invalid server certificate.',
        );
      case DioExceptionType.cancel:
        return const ApiException('The request was cancelled.');
      case DioExceptionType.badResponse:
        final status = error.response?.statusCode;
        final data = error.response?.data;
        String? detail;
        if (data is Map && data['detail'] != null) {
          detail = data['detail'].toString();
        }
        if (status == 401) {
          return ApiException(
            detail ?? 'Session expired or unauthorized. Please sign in again.',
            statusCode: status,
          );
        }
        if (status == 403) {
          return ApiException(
            detail ?? 'You do not have permission to perform this action.',
            statusCode: status,
          );
        }
        if (status == 404) {
          return ApiException(
            detail ?? 'Requested resource was not found.',
            statusCode: status,
          );
        }
        return ApiException(
          detail ?? 'Server returned an unexpected error (${status ?? 'unknown'}).',
          statusCode: status,
        );
      case DioExceptionType.unknown:
        return const ApiException(
          'Unable to reach the JobMail server. Please check your network connection.',
          isOffline: true,
        );
    }
  }
}
