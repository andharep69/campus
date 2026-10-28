import os, sqlite3, secrets, re
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "campusfind.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_UPLOAD_BYTES = 4 * 1024 * 1024

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("CAMPUSFIND_SECRET_KEY", "dev-only-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)

CATEGORIES = ["Electronics", "Books & Notes", "Bags", "Keys", "ID Cards", "Clothing", "Accessories", "Water Bottles", "Other"]
STATUSES = ["Lost", "Found"]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            item_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Lost','Found')),
            photo TEXT,
            contact_preference TEXT NOT NULL DEFAULT 'in_app',
            state TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            claimant_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            reporter_id INTEGER NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        # Demo admin is created only if configured with environment variables.
        admin_email = os.environ.get("CAMPUSFIND_ADMIN_EMAIL", "").strip().lower()
        admin_password = os.environ.get("CAMPUSFIND_ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            row = conn.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    ("CampusFind Admin", admin_email, generate_password_hash(admin_password), "admin", datetime.utcnow().isoformat())
                )

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with db() as conn:
        return conn.execute("SELECT id,name,email,role FROM users WHERE id=?", (uid,)).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_globals():
    return {"current_user": current_user(), "categories": CATEGORIES}

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "").strip()
    location = request.args.get("location", "").strip()
    query = "SELECT items.*, users.name AS poster_name FROM items JOIN users ON users.id=items.user_id WHERE items.state='Open'"
    args = []
    if q:
        query += " AND (items.name LIKE ? OR items.description LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if category in CATEGORIES:
        query += " AND items.category=?"
        args.append(category)
    if status in STATUSES:
        query += " AND items.status=?"
        args.append(status)
    if location:
        query += " AND items.location LIKE ?"
        args.append(f"%{location}%")
    query += " ORDER BY items.created_at DESC"
    with db() as conn:
        items = conn.execute(query, args).fetchall()
        stats = {
            "lost": conn.execute("SELECT COUNT(*) FROM items WHERE status='Lost' AND state='Open'").fetchone()[0],
            "found": conn.execute("SELECT COUNT(*) FROM items WHERE status='Found' AND state='Open'").fetchone()[0],
            "returned": conn.execute("SELECT COUNT(*) FROM items WHERE state='Returned'").fetchone()[0]
        }
    return render_template("index.html", items=items, stats=stats, filters={"q":q,"category":category,"status":status,"location":location})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a name and a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        else:
            try:
                with db() as conn:
                    conn.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                                 (name, email, generate_password_hash(password), datetime.utcnow().isoformat()))
                flash("Account created. You can now sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(24)
            flash(f"Welcome back, {user['name']}!", "success")
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("index"))
        flash("Email or password was not recognized.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("index"))

@app.route("/report/<status>", methods=["GET", "POST"])
@login_required
def report_item(status):
    if status not in STATUSES:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        item_date = request.form.get("item_date", "")
        contact_preference = request.form.get("contact_preference", "in_app")
        photo_name = None
        if not name or category not in CATEGORIES or len(description) < 8 or not location or not item_date:
            flash("Please complete all required fields. Description must be at least 8 characters.", "error")
            return render_template("report.html", status=status)
        photo = request.files.get("photo")
        if photo and photo.filename:
            if not allowed_file(photo.filename):
                flash("Photo must be PNG, JPG, JPEG, or WEBP.", "error")
                return render_template("report.html", status=status)
            ext = photo.filename.rsplit(".", 1)[1].lower()
            photo_name = secrets.token_hex(16) + "." + ext
            photo.save(os.path.join(UPLOAD_DIR, photo_name))
        user = current_user()
        with db() as conn:
            conn.execute("""INSERT INTO items(user_id,name,category,description,location,item_date,status,photo,contact_preference,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                         (user["id"], name[:100], category, description[:1500], location[:150], item_date, status,
                          photo_name, contact_preference if contact_preference in ("in_app","campus_desk") else "in_app",
                          datetime.utcnow().isoformat()))
        flash("Your report has been published.", "success")
        return redirect(url_for("index"))
    return render_template("report.html", status=status)

@app.route("/item/<int:item_id>")
def item_detail(item_id):
    with db() as conn:
        item = conn.execute("SELECT items.*, users.name AS poster_name FROM items JOIN users ON users.id=items.user_id WHERE items.id=?", (item_id,)).fetchone()
        if not item:
            abort(404)
        claims = []
        user = current_user()
        if user and (user["id"] == item["user_id"] or user["role"] == "admin"):
            claims = conn.execute("SELECT claims.*, users.name AS claimant_name FROM claims JOIN users ON users.id=claims.claimant_id WHERE item_id=? ORDER BY claims.created_at DESC", (item_id,)).fetchall()
    return render_template("item.html", item=item, claims=claims)

@app.route("/item/<int:item_id>/claim", methods=["POST"])
@login_required
def claim_item(item_id):
    message = request.form.get("message", "").strip()
    user = current_user()
    with db() as conn:
        item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            abort(404)
        if item["user_id"] == user["id"]:
            flash("You cannot claim your own report.", "error")
        elif item["state"] != "Open":
            flash("This item is no longer open for claims.", "error")
        elif len(message) < 12:
            flash("Please provide a little more detail so the owner can verify your claim.", "error")
        else:
            conn.execute("INSERT INTO claims(item_id,claimant_id,message,created_at) VALUES(?,?,?,?)",
                         (item_id, user["id"], message[:1200], datetime.utcnow().isoformat()))
            flash("Claim submitted privately to the report owner for verification.", "success")
    return redirect(url_for("item_detail", item_id=item_id))

@app.route("/claim/<int:claim_id>/status", methods=["POST"])
@login_required
def claim_status(claim_id):
    action = request.form.get("action")
    user = current_user()
    with db() as conn:
        claim = conn.execute("SELECT claims.*, items.user_id AS owner_id, items.id AS item_id FROM claims JOIN items ON items.id=claims.item_id WHERE claims.id=?", (claim_id,)).fetchone()
        if not claim:
            abort(404)
        if user["id"] != claim["owner_id"] and user["role"] != "admin":
            abort(403)
        if action not in ("Approved", "Rejected"):
            abort(400)
        conn.execute("UPDATE claims SET status=? WHERE id=?", (action, claim_id))
        if action == "Approved":
            conn.execute("UPDATE items SET state='Returned' WHERE id=?", (claim["item_id"],))
        flash(f"Claim {action.lower()}.", "success")
    return redirect(url_for("item_detail", item_id=claim["item_id"]))

@app.route("/item/<int:item_id>/close", methods=["POST"])
@login_required
def close_item(item_id):
    user = current_user()
    with db() as conn:
        item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            abort(404)
        if item["user_id"] != user["id"] and user["role"] != "admin":
            abort(403)
        conn.execute("UPDATE items SET state='Returned' WHERE id=?", (item_id,))
    flash("Report marked as returned/closed.", "success")
    return redirect(url_for("item_detail", item_id=item_id))

@app.route("/my-reports")
@login_required
def my_reports():
    user = current_user()
    with db() as conn:
        items = conn.execute("SELECT * FROM items WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        claims = conn.execute("SELECT claims.*, items.name AS item_name, items.status AS item_status FROM claims JOIN items ON items.id=claims.item_id WHERE claims.claimant_id=? ORDER BY claims.created_at DESC", (user["id"],)).fetchall()
    return render_template("my_reports.html", items=items, claims=claims)

@app.route("/item/<int:item_id>/report", methods=["POST"])
@login_required
def report_listing(item_id):
    reason = request.form.get("reason", "").strip()
    user = current_user()
    if len(reason) < 4:
        flash("Please describe the concern.", "error")
        return redirect(url_for("item_detail", item_id=item_id))
    with db() as conn:
        item = conn.execute("SELECT id FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            abort(404)
        conn.execute("INSERT INTO reports(item_id,reporter_id,reason,created_at) VALUES(?,?,?,?)",
                     (item_id, user["id"], reason[:500], datetime.utcnow().isoformat()))
    flash("Listing reported to the moderation team.", "success")
    return redirect(url_for("item_detail", item_id=item_id))

@app.route("/admin")
@login_required
@admin_required
def admin():
    with db() as conn:
        reports = conn.execute("SELECT reports.*, items.name AS item_name, users.name AS reporter_name FROM reports JOIN items ON items.id=reports.item_id JOIN users ON users.id=reports.reporter_id ORDER BY reports.created_at DESC").fetchall()
        items = conn.execute("SELECT items.*, users.name AS poster_name FROM items JOIN users ON users.id=items.user_id ORDER BY items.created_at DESC").fetchall()
    return render_template("admin.html", reports=reports, items=items)

@app.route("/admin/item/<int:item_id>/remove", methods=["POST"])
@login_required
@admin_required
def admin_remove(item_id):
    with db() as conn:
        conn.execute("UPDATE items SET state='Removed' WHERE id=?", (item_id,))
    flash("Listing removed from public browsing.", "success")
    return redirect(url_for("admin"))

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # Filenames are random tokens; only validated image extensions are saved.
    return send_from_directory(UPLOAD_DIR, filename)

@app.errorhandler(403)
def forbidden(_):
    return render_template("message.html", title="Access denied", message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("message.html", title="Page not found", message="We couldn't find that page."), 404

@app.errorhandler(413)
def too_large(_):
    flash("Upload is too large. Please use an image under 4 MB.", "error")
    return redirect(request.referrer or url_for("index"))

init_db()

if __name__ == "__main__":
    # For local development only. Do not use debug mode in production.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
