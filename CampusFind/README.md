# CampusFind — Campus Lost & Found

A responsive Flask + SQLite MVP for campus lost-and-found reports. Includes registration/login, listing search and filters, private claim submissions, claim approval/rejection, user dashboard, reports/moderation, and optional item photos.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## First use

1. Create a student account from **Create account**.
2. Sign in.
3. Report a lost or found item.
4. Search/filter listings and open a listing to submit a private claim.
5. The listing owner can approve/reject claims or close a report.
6. A report submitted with the “Report this listing” option appears in the admin dashboard.

## Configure an administrator

Set these environment variables **before first launch** (or before restarting if the admin account does not exist yet):

```bash
# macOS/Linux
export CAMPUSFIND_ADMIN_EMAIL="admin@yourcollege.edu"
export CAMPUSFIND_ADMIN_PASSWORD="use-a-unique-long-password"
export CAMPUSFIND_SECRET_KEY="generate-a-long-random-secret"
python app.py
```

Windows PowerShell:
```powershell
$env:CAMPUSFIND_ADMIN_EMAIL="admin@yourcollege.edu"
$env:CAMPUSFIND_ADMIN_PASSWORD="use-a-unique-long-password"
$env:CAMPUSFIND_SECRET_KEY="generate-a-long-random-secret"
python app.py
```

The admin account is created on app startup only when both admin email and password are configured and that email is not already registered.

## Storage and privacy

- SQLite stores accounts, item listings, claims, and moderation reports in `campusfind.db`.
- Uploaded image files are stored in `uploads/`; supported formats are PNG, JPG, JPEG, and WEBP, with a 4 MB request upload limit.
- Email addresses and phone numbers are not shown in public listing pages. Claims are visible to the listing owner and admin.
- The app uses Werkzeug password hashing and role checks for admin routes.

## Important before production deployment

This is a hackathon MVP, not a production-audited service. Before exposing it publicly:
- Set a strong random `CAMPUSFIND_SECRET_KEY`; never use the development fallback.
- Use HTTPS and secure cookie settings; configure trusted-host and reverse-proxy settings for your host.
- Add CSRF protection to all state-changing forms, login rate limiting, password reset/email verification, and stronger abuse prevention.
- Use a production WSGI server (e.g. Gunicorn), not Flask's development server.
- Use managed database and private object storage if deploying to multiple instances; local SQLite/uploads may not persist on some hosts.
- Add retention/deletion workflows, privacy notice/consent, and campus policy review.
- Do not post secret identifying details about valuable items publicly. Verify ownership before physical handover.
- The current report/claim status actions are basic MVP flows; add audit logging and more robust moderation before real-world use.

## Project structure

```text
CampusFind/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── auth.html
│   ├── report.html
│   ├── item.html
│   ├── my_reports.html
│   ├── admin.html
│   └── message.html
├── static/
│   └── style.css
└── uploads/
```
