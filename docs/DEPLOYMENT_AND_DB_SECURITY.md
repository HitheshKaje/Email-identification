# JobMail – Production Deployment, Database Security & Recovery Guide

## 1. Environment Separation
- **Development (`ENVIRONMENT=development`):** Uses local `backend/.env` (never committed), `http://localhost:8000` / `http://localhost:8080`.
- **Staging (`ENVIRONMENT=staging`):** Uses dedicated staging MongoDB cluster, staging OAuth credentials, HTTPS callback `https://api-staging.yourdomain.com/auth/google/callback`, and strict domain CORS.
- **Production (`ENVIRONMENT=production`):** Enforced startup assertions in `backend/app/core/config.py` fail fast if:
  - `DEBUG=true`
  - `JWT_SECRET_KEY` is missing, placeholder, or `< 32` chars
  - `TOKEN_ENCRYPTION_KEY` / `TOKEN_ENCRYPTION_KEYS` is missing or invalid
  - Any URL/origin (`GOOGLE_REDIRECT_URI`, `FRONTEND_URL`, `CORS_ORIGINS`) contains `localhost`, `127.0.0.1`, `0.0.0.0`, or wildcard `*`
  - `GOOGLE_REDIRECT_URI` does not start with `https://`

## 2. Database Authentication, Least Privilege & TLS (Phase 12)
1. **Authentication & Least-Privilege Role:** Create a dedicated MongoDB database user (`jobmail_app`) scoped strictly to `readWrite` on the single application database (`jobmail_prod`), never `root` or `dbAdminAnyDatabase`:
   ```js
   use jobmail_prod
   db.createUser({
     user: "jobmail_app",
     pwd: "<strong-managed-secret>",
     roles: [{ role: "readWrite", db: "jobmail_prod" }]
   })
   ```
2. **TLS/SSL:** Use `mongodb+srv://...` (auto-enables `tls=True` in `MongoDatabaseManager`) or set `MONGODB_TLS_CA_FILE`.
3. **Network Restrictions & Connection Pool Limits:** Restrict MongoDB inbound access via VPC peering / security group allowlist (backend API servers only) and tune `MONGODB_MAX_POOL_SIZE` (default `50`).
4. **Encrypted Backups & Recovery:**
   - Enable automated daily encrypted snapshots in MongoDB Atlas / cloud volume KMS.
   - Store encrypted backup archives separately from `TOKEN_ENCRYPTION_KEY` (backing up DB without the KMS/secret manager key prevents raw token decryption).
   - Periodically test point-in-time recovery into staging before applying schema migrations.
5. **Non-Destructive Migrations:** Apply additive index creation via `ensure_indexes()` (`create_index` is idempotent) and run key rotations via `backend/scripts/rotate_encryption_keys.py` with `TOKEN_ENCRYPTION_KEYS="<new_key>,<old_key>"`.

## 3. Secrets & Key Rotation (Phase 4 & 13)
- Store `JWT_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_SECRET`, `MONGODB_URI`, and `SMTP_PASSWORD` in GCP Secret Manager / AWS Secrets Manager / HashiCorp Vault (mounted or injected at runtime).
- **Encryption Key Rotation Procedure:**
  1. Generate a new Fernet key (`Fernet.generate_key().decode()`).
  2. Deploy with `TOKEN_ENCRYPTION_KEYS="<new_key>,<old_key>"` (`MultiFernet` encrypts new writes with `<new_key>` while reading both).
  3. Run `python backend/scripts/rotate_encryption_keys.py` to re-encrypt all stored tokens, MFA secrets, and email ciphertexts.
  4. Remove `<old_key>` once verified.

## 4. Network, Firewall & Reverse Proxy Controls
- Expose ONLY ports `80` (301 redirect) and `443` (HTTPS) publicly on `deploy/nginx.conf`.
- Keep FastAPI (`8000`), MongoDB (`27017`), and optional Redis private inside `jobmail_internal` / VPC subnet.
- Set `TRUSTED_HOSTS` and `ENABLE_API_DOCS=false` in production so Swagger UI/OpenAPI are disabled publicly.
