from flask import Flask, render_template_string, request, redirect, url_for, session
import json, os, hashlib
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-to-something-random-123"

DATA_DIR = "/data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")

def load(file, default):
    os.makedirs(os.path.dirname(file), exist_ok=True)
    if not os.path.exists(file):
        with open(file, "w") as f: json.dump(default, f)
    with open(file, "r") as f: return json.load(f)

def save(file, data):
    with open(file, "w") as f: json.dump(data, f, indent=2)

def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

BASE_HTML = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TaskFlow</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
body{font-family:'Inter',sans-serif;background:#0f0f0f;color:#fff}
</style>
</head>
<body class="min-h-screen pb-20">
<div class="max-w-2xl mx-auto p-4">
{{content|safe}}
</div>

<!-- Bottom Nav -->
<div class="fixed bottom-0 left-0 right-0 bg-[#1a1a1a] border-t border-gray-800">
  <div class="flex justify-around py-3 max-w-2xl mx-auto">
    <a href="/" class="flex flex-col items-center text-xs {% if page=='home' %}text-purple-500{% else %}text-gray-400{% endif %}">
      <svg class="w-6 h-6 mb-1" fill="currentColor" viewBox="0 0 20 20"><path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/></svg>
      Home
    </a>
    <a href="/dashboard" class="flex flex-col items-center text-xs {% if page=='dashboard' %}text-purple-500{% else %}text-gray-400{% endif %}">
      <svg class="w-6 h-6 mb-1" fill="currentColor" viewBox="0 0 20 20"><path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"/></svg>
      Dashboard
    </a>
    <a href="/tasks" class="flex flex-col items-center text-xs {% if page=='tasks' %}text-purple-500{% else %}text-gray-400{% endif %}">
      <svg class="w-6 h-6 mb-1" fill="currentColor" viewBox="0 0 20 20"><path d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"/></svg>
      Tasks
    </a>
    <a href="/settings" class="flex flex-col items-center text-xs {% if page=='settings' %}text-purple-500{% else %}text-gray-400{% endif %}">
      <svg class="w-6 h-6 mb-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.958c-1.525-.611-3.05 1.084-2.439 2.609.305.764.71 1.47 1.208 2.106a1.534 1.534 0 01-.642 2.33c-1.668.879-1.37 3.366.383 3.96.657.21 1.335.34 2.028.38a1.536 1.536 0 01.801.724l.793 1.588c.607 1.214 2.325 1.214 2.932 0l.793-1.588a1.534 1.534 0 01.801-.724c.692-.04 1.371-.17 2.028-.38 1.754-.594 2.052-3.08.383-3.96a1.534 1.534 0 01-.642-2.33c.498-.636.902-1.342 1.207-2.106.611-1.525-1.084-3.05-2.439-2.609a1.534 1.534 0 01-2.287-.958zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/></svg>
      Settings
    </a>
  </div>
</div>
</body>
</html>
"""

AUTH_HTML = """
<div class="pt-20">
  <h1 class="text-3xl font-bold text-center mb-2">Hi, I'm TaskFlow</h1>
  <p class="text-gray-400 text-center mb-8">How can I help you today?</p>

  <div class="bg-[#1a1a1a] rounded-2xl p-4 flex items-center gap-3">
    <svg class="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/></svg>
    <form method="post" action="/login" class="flex-1 flex gap-2">
      <input name="email" type="email" placeholder="Enter email..." required class="flex-1 bg-transparent outline-none">
      <input name="password" type="password" placeholder="Password" required class="w-24 bg-transparent outline-none">
      <button class="text-purple-500">→</button>
    </form>
  </div>

  {% if msg %}<div class="text-red-500 text-center mt-4">{{msg}}</div>{% endif %}
  <p class="text-center mt-4 text-gray-500">No account? <a href="/signup" class="text-purple-500">Sign up</a></p>
</div>
"""

@app.route("/")
def home():
    if "email" not in session:
        return render_template_string(BASE_HTML, content=AUTH_HTML, page='home')
    return render_template_string(BASE_HTML, content="<h2 class='text-2xl font-bold'>Home</h2><p class='text-gray-400 mt-2'>Welcome back, {}</p>".format(session['username']), page='home')

@app.route("/dashboard")
def dashboard():
    if "email" not in session: return redirect("/")
    tasks = load(TASKS_FILE, [])
    user_tasks = [t for t in tasks if t["email"] == session["email"]]
    done = len([t for t in user_tasks if t["done"]])
    content = f"<h2 class='text-2xl font-bold'>Dashboard</h2><div class='mt-4 bg-[#1a1a1a] p-4 rounded-xl'><p>Total: {len(user_tasks)}</p><p>Done: {done}</p><p>Pending: {len(user_tasks)-done}</p></div>"
    return render_template_string(BASE_HTML, content=content, page='dashboard')

@app.route("/tasks")
def tasks():
    if "email" not in session: return redirect("/")
    tasks = load(TASKS_FILE, [])
    user_tasks = [t for t in tasks if t["email"] == session["email"]]
    html = "<h2 class='text-2xl font-bold mb-4'>Tasks</h2><form method='post' action='/add' class='mb-4 flex gap-2'><input name='title' placeholder='Add task...' required class='flex-1 bg-[#1a1a1a] p-3 rounded-xl'><button class='bg-purple-600 px-4 rounded-xl'>Add</button></form>"
    for t in user_tasks:
        html += f"<div class='bg-[#1a1a1a] p-3 rounded-xl mb-2 flex justify-between'><span class={'line-through' if t['done'] else ''}>{t['title']}</span><div><a href='/toggle/{t['id']}' class='text-green-500 mr-3'>✓</a><a href='/delete/{t['id']}' class='text-red-500'>✕</a></div></div>"
    return render_template_string(BASE_HTML, content=html, page='tasks')

@app.route("/settings")
def settings():
    if "email" not in session: return redirect("/")
    content = "<h2 class='text-2xl font-bold'>Settings</h2><div class='mt-4 space-y-3'><a href='/privacy' class='block bg-[#1a1a1a] p-3 rounded-xl'>Privacy</a><a href='/logout' class='block bg-[#1a1a1a] p-3 rounded-xl text-red-500'>Logout</a></div>"
    return render_template_string(BASE_HTML, content=content, page='settings')

@app.route("/privacy")
def privacy():
    content = "<h2 class='text-2xl font-bold'>Privacy</h2><p class='text-gray-400 mt-2'>Your data is stored locally in your Render disk. We don’t share it.</p>"
    return render_template_string(BASE_HTML, content=content, page='settings')

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].lower()
        users = load(USERS_FILE, [])
        if any(u["email"] == email for u in users):
            return render_template_string(BASE_HTML, content=AUTH_HTML.replace("Sign up","Log in").replace("/signup","/login"), msg="Email exists")
        users.append({"username": email.split('@')[0], "email": email, "password": hash_pass(request.form["password"])})
        save(USERS_FILE, users)
        session["email"] = email
        session["username"] = email.split('@')[0]
        return redirect("/")
    return render_template_string(BASE_HTML, content=AUTH_HTML.replace("Log in","Sign up").replace("/login","/signup"), page='home')

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].lower()
    password = hash_pass(request.form["password"])
    users = load(USERS_FILE, [])
    user = next((u for u in users if u["email"]==email and u["password"]==password), None)
    if user:
        session["email"] = email
        session["username"] = user["username"]
        return redirect("/")
    return render_template_string(BASE_HTML, content=AUTH_HTML, msg="Invalid credentials", page='home')

@app.route("/add", methods=["POST"])
def add():
    tasks = load(TASKS_FILE, [])
    new_id = max([t["id"] for t in tasks], default=0) + 1
    tasks.append({"id": new_id, "title": request.form["title"], "done": False, "email": session["email"]})
    save(TASKS_FILE, tasks)
    return redirect("/tasks")

@app.route("/toggle/<int:tid>")
def toggle(tid):
    tasks = load(TASKS_FILE, [])
    for t in tasks:
        if t["id"] == tid and t["email"] == session["email"]:
            t["done"] = not t["done"]
            break
    save(TASKS_FILE, tasks)
    return redirect("/tasks")

@app.route("/delete/<int:tid>")
def delete(tid):
    tasks = load(TASKS_FILE, [])
    tasks = [t for t in tasks if not (t["id"] == tid and t["email"] == session["email"])]
    save(TASKS_FILE, tasks)
    return redirect("/tasks")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
