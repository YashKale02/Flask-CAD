from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv
from waitress import serve

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

# MongoDB setup with error handling
try:
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    # Test connection
    client.admin.command('ping')
    db = client.placement_db
    users_collection = db.users
    jobs_collection = db.jobs
    applications_collection = db.applications
    print("✅ MongoDB connected successfully!")
except ConnectionFailure as e:
    print("❌ MongoDB connection failed!")
    print(f"Error: {e}")
    print("\n⚠️  Please check your MONGO_URI in .env file")
    exit(1)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('user_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_email' in session:
        if session.get('user_role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Check if user already exists
        if users_collection.find_one({'email': email}):
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            'name': name,
            'email': email,
            'password': hashed_password,
            'role': role,
            'created_at': datetime.now()
        })
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = users_collection.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            session['user_email'] = user['email']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            
            flash(f'Welcome {user["name"]}!', 'success')
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

# Admin Routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    jobs = list(jobs_collection.find().sort('posted_at', -1))
    
    # Count applicants for each job
    for job in jobs:
        job['applicant_count'] = applications_collection.count_documents({'job_id': job['_id']})
    
    return render_template('admin.html', jobs=jobs)

@app.route('/admin/add-job', methods=['POST'])
@admin_required
def add_job():
    title = request.form.get('title')
    job_type = request.form.get('type')
    company = request.form.get('company')
    description = request.form.get('description')
    
    jobs_collection.insert_one({
        'title': title,
        'type': job_type,
        'company': company,
        'description': description,
        'posted_by': session['user_email'],
        'posted_at': datetime.now()
    })
    
    flash('Job posted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-job/<job_id>')
@admin_required
def delete_job(job_id):
    jobs_collection.delete_one({'_id': ObjectId(job_id)})
    applications_collection.delete_many({'job_id': ObjectId(job_id)})
    flash('Job deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/applicants/<job_id>')
@admin_required
def view_applicants(job_id):
    job = jobs_collection.find_one({'_id': ObjectId(job_id)})
    applicants = list(applications_collection.find({'job_id': ObjectId(job_id)}).sort('applied_at', -1))
    
    return render_template('applicants.html', job=job, applicants=applicants)

# User Routes
@app.route('/user')
@login_required
def user_dashboard():
    if session.get('user_role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    jobs = list(jobs_collection.find().sort('posted_at', -1))
    
    # Check which jobs user has applied to
    user_applications = list(applications_collection.find({'user_email': session['user_email']}))
    applied_job_ids = [str(app['job_id']) for app in user_applications]
    
    return render_template('user.html', jobs=jobs, applied_job_ids=applied_job_ids, my_applications=user_applications)

@app.route('/user/apply/<job_id>', methods=['POST'])
@login_required
def apply_job(job_id):
    # Check if already applied
    existing_application = applications_collection.find_one({
        'job_id': ObjectId(job_id),
        'user_email': session['user_email']
    })
    
    if existing_application:
        flash('You have already applied to this job', 'warning')
        return redirect(url_for('user_dashboard'))
    
    # Handle file upload
    if 'resume' not in request.files:
        flash('No resume file uploaded', 'danger')
        return redirect(url_for('user_dashboard'))
    
    file = request.files['resume']
    
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('user_dashboard'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{session['user_email']}_{job_id}_{file.filename}")
        #.
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        web_path = f"uploads/{filename}"

        # Create application
        applications_collection.insert_one({
            'job_id': ObjectId(job_id),
            'user_email': session['user_email'],
            'user_name': session['user_name'],
            'resume_path': web_path,
            'applied_at': datetime.now()
        })
        #.
        
        flash('Application submitted successfully!', 'success')
    else:
        flash('Invalid file type. Only PDF, DOC, DOCX allowed', 'danger')
    
    return redirect(url_for('user_dashboard'))

if __name__ == '__main__':
    print("✅ MongoDB connected successfully!")
    print("Jenkins Setup Complete!")
    print("🚀 Starting Flask application with Waitress server...")
    print(f"📁 Upload folder: {app.config['UPLOAD_FOLDER']}")
    print("🌐 Access at: http://127.0.0.1:5000")
    serve(app, host='0.0.0.0', port=5000)