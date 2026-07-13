# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly by emailing security@tetranoodle.com. Do not open a public issue.

## Security Measures

### Authentication
- JWT-based stateless authentication with 8-hour token expiry
- PBKDF2-SHA256 password hashing with 600,000 iterations and 32-byte random salt
- Bearer token validation on all protected endpoints

### Authorization
- Role-based access control (RBAC) by department
- Connector access scoped per department
- Session ownership validation prevents cross-user access

### Input Validation
- Message length capped at 10,000 characters
- Document context capped at 50,000 characters
- File uploads: extension whitelist + MIME type validation
- Filename sanitization with UUID prefix to prevent path traversal
- Resolved file paths verified to stay within upload directory

### Transport & Headers
- CORS restricted to configured origins with explicit method/header allowlists
- Security headers on all responses:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- Content Security Policy (CSP) on frontend

### Rate Limiting
- Global: 30 requests/minute per IP
- OAuth endpoints: 5 requests/minute per IP
- OAuth callback: 10 requests/minute per IP

### OAuth & Connectors
- PKCE (S256) for all OAuth flows
- Scoped `postMessage` origin (no wildcard)
- Origin validation on incoming message events
- State tokens with 10-minute expiry
- HTML-escaped OAuth callback responses to prevent XSS

### Prompt Injection Mitigation
- Memory context sanitized before injection into system prompts
- Common injection patterns filtered
- Memory content wrapped in explicit data boundary markers

### Container Security
- Backend runs as non-root `appuser`
- Frontend runs as non-root `nextjs` user
- Minimal base images (python:3.12-slim, node:20-alpine)

## Dependency Management

Run periodic audits:

```bash
# Backend
cd backend && pip audit

# Frontend
cd frontend && npm audit
```
