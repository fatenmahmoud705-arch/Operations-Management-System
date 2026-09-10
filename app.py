from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_operations_key'

def get_db_connection():
    conn = sqlite3.connect('operations.db')
    conn.row_factory = sqlite3.Row
    return conn

# تهيئة قاعدة البيانات وإنشاء الجداول تلقائيًا
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. جدول الأقسام
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        department_id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_name TEXT NOT NULL UNIQUE
    )''')
    
    # 2. جدول الموظفين والمستخدمين
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'Employee',
        department_id INTEGER,
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    )''')
    
    # 3. جدول المهام
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        assigned_to INTEGER,
        status TEXT DEFAULT 'Pending',
        FOREIGN KEY (assigned_to) REFERENCES users(user_id)
    )''')
    
    # إضافة قسم ومستخدم Admin افتراضي للتجربة
    cursor.execute("INSERT OR IGNORE INTO departments (department_id, department_name) VALUES (1, 'Operations')")
    admin_password = generate_password_hash('admin123')
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, email, password_hash, role, department_id) VALUES (1, 'System Admin', 'admin@company.com', ?, 'Admin', 1)", (admin_password,))
    
    conn.commit()
    conn.close()

# ----------------- AUTHENTICATION & DASHBOARD ----------------- #

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash('بيانات الدخول غير صحيحة!')
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    total_employees = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_tasks = conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    completed_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Completed'").fetchone()[0]
    conn.close()
    
    return render_template('dashboard.html', 
                           total_employees=total_employees, 
                           total_tasks=total_tasks, 
                           completed_tasks=completed_tasks)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------- EMPLOYEES MANAGEMENT ----------------- #

@app.route('/employees')
def list_employees():
    if 'user_id' not in session or session.get('role') != 'Admin':
        flash('غير مصرح لك بالوصول لهذه الصفحة!')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    employees = conn.execute('''
        SELECT users.user_id, users.full_name, users.email, users.role, departments.department_name 
        FROM users 
        LEFT JOIN departments ON users.department_id = departments.department_id
    ''').fetchall()
    departments = conn.execute('SELECT * FROM departments').fetchall()
    conn.close()
    
    return render_template('employees.html', employees=employees, departments=departments)

@app.route('/employees/add', methods=['POST'])
def add_employee():
    if 'user_id' not in session or session.get('role') != 'Admin':
        return redirect(url_for('dashboard'))
        
    full_name = request.form['full_name']
    email = request.form['email']
    password = generate_password_hash(request.form['password'])
    role = request.form['role']
    department_id = request.form['department_id']
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (full_name, email, password_hash, role, department_id) VALUES (?, ?, ?, ?, ?)',
                     (full_name, email, password, role, department_id))
        conn.commit()
        flash('تمت إضافة الموظف بنجاح!')
    except sqlite3.IntegrityError:
        flash('البريد الإلكتروني موجود بالفعل!')
    finally:
        conn.close()
        
    return redirect(url_for('list_employees'))

# ----------------- TASKS MANAGEMENT ----------------- #

@app.route('/tasks')
def list_tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    if session.get('role') in ['Admin', 'Manager']:
        tasks = conn.execute('''
            SELECT tasks.task_id, tasks.title, tasks.status, users.full_name as assigned_name
            FROM tasks
            LEFT JOIN users ON tasks.assigned_to = users.user_id
        ''').fetchall()
    else:
        tasks = conn.execute('''
            SELECT tasks.task_id, tasks.title, tasks.status, users.full_name as assigned_name
            FROM tasks
            LEFT JOIN users ON tasks.assigned_to = users.user_id
            WHERE tasks.assigned_to = ?
        ''', (session['user_id'],)).fetchall()
        
    users = conn.execute('SELECT user_id, full_name FROM users').fetchall()
    conn.close()
    
    return render_template('tasks.html', tasks=tasks, users=users)

@app.route('/tasks/add', methods=['POST'])
def add_task():
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Manager']:
        return redirect(url_for('dashboard'))
        
    title = request.form['title']
    assigned_to = request.form['assigned_to']
    
    conn = get_db_connection()
    conn.execute('INSERT INTO tasks (title, assigned_to) VALUES (?, ?)', (title, assigned_to))
    conn.commit()
    conn.close()
    
    flash('تم تعيين المهمة بنجاح!')
    return redirect(url_for('list_tasks'))

@app.route('/tasks/update_status/<int:task_id>', methods=['POST'])
def update_task_status(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    new_status = request.form['status']
    conn = get_db_connection()
    conn.execute('UPDATE tasks SET status = ? WHERE task_id = ?', (new_status, task_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('list_tasks'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)