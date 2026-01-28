# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Dynamic-KB, please report it responsibly.

### How to Report

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Instead, please report via one of these methods:
   - Open a [private security advisory](https://github.com/maciej-konczal/dynamic-kb/security/advisories/new) on GitHub
   - Email the maintainer directly (see profile)

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

### Response Timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Fix timeline**: Depends on severity, typically within 30 days for critical issues

### Scope

This security policy covers:
- The Dynamic-KB application code
- Docker configurations
- CI/CD workflows

This policy does **not** cover:
- Third-party dependencies (report to their maintainers)
- ElevenLabs API (report to ElevenLabs)
- Google Gemini API (report to Google)

## Security Best Practices

When using Dynamic-KB:

1. **API Keys**: Never commit API keys to version control. Use `.env` files or environment variables.
2. **Database**: If using Supabase, ensure Row Level Security (RLS) is enabled for production.
3. **Deployment**: Use HTTPS in production environments.
4. **Updates**: Keep dependencies up to date by running `pip install -U -r requirements.txt` regularly.
