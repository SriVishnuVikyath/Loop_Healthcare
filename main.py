import os
from flask import Flask, render_template_string, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt
from functools import wraps

# --- App Setup ---

app = Flask(__name__)
# Get the absolute path of the directory where the script is located
basedir = os.path.abspath(os.path.dirname(__file__))
# Configure the database
app.config['SECRET_KEY'] = 'a_very_secret_key_that_you_should_change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Extensions ---

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # The route function name for the login page
login_manager.login_message_category = 'info'

# --- Database Models ---

# UserMixin is required by Flask-Login
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    # Role will be 'patient', 'doctor', or 'insurance'
    role = db.Column(db.String(20), nullable=False)

    # Relationships to link to profile tables
    patient_profile = db.relationship('PatientProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    doctor_profile = db.relationship('DoctorProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    insurance_profile = db.relationship('InsuranceProfile', backref='user', uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"User('{self.email}', '{self.role}')"

class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default='Unnamed')
    address = db.Column(db.String(200))
    # You can add medical_history_summary, dob, etc. here
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Relationships for records and appointments
    records = db.relationship('MedicalRecord', backref='patient', lazy=True, foreign_keys='MedicalRecord.patient_id')
    appointments = db.relationship('Appointment', backref='patient', lazy=True, foreign_keys='Appointment.patient_id')


class DoctorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default='Dr. Unnamed')
    specialty = db.Column(db.String(100))
    practice_address = db.Column(db.String(200))
    # You will add latitude/longitude here for the "nearby" search
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Relationships for records and appointments
    records_written = db.relationship('MedicalRecord', backref='doctor', lazy=True, foreign_keys='MedicalRecord.doctor_id')
    appointments = db.relationship('Appointment', backref='doctor', lazy=True, foreign_keys='Appointment.doctor_id')


class InsuranceProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False, default='Unnamed Company')
    company_address = db.Column(db.String(200))
    # Add other relevant fields for the insurance provider
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)


class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    diagnosis = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    prescription = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending') # e.g., Pending, Confirmed
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)


# --- Flask-Login Helper ---

@login_manager.user_loader
def load_user(user_id):
    """Required by Flask-Login to load the current user from session."""
    return db.session.get(User, int(user_id))

# --- Role-Specific Decorators ---
# These decorators protect routes from being accessed by the wrong user role

def patient_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'patient':
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def doctor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'doctor':
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def insurance_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'insurance':
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function


# --- HTML Templates (as strings) ---
# In a real app, these would be in separate .html files and loaded with render_template()

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Health App</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; }
        nav { background-color: #333; padding: 10px; border-radius: 8px; }
        nav a { color: white; text-decoration: none; padding: 10px 15px; }
        nav a:hover { background-color: #555; }
        .container { background-color: white; padding: 20px; border-radius: 8px; margin-top: 20px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; }
        .form-group input, .form-group select { width: 300px; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        .btn { background-color: #007bff; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
        .btn:hover { background-color: #0056b3; }
        .alert { padding: 15px; margin-bottom: 20px; border-radius: 4px; }
        .alert-info { background-color: #d1ecf1; border-color: #bee5eb; color: #0c5460; }
        .alert-danger { background-color: #f8d7da; border-color: #f5c6cb; color: #721c24; }
    </style>
</head>
<body>
    <nav>
        <a href="{{ url_for('home') }}">Home</a>
        {% if current_user.is_authenticated %}
            <a href="{{ url_for('dashboard') }}">Dashboard</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
            <a href="{{ url_for('login') }}">Login</a>
            <a href="{{ url_for('register') }}">Register</a>
        {% endif %}
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

HTML_HOME = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
    <h1>Welcome to the Health App</h1>
    <p>This is the main homepage. Please log in or register to continue.</p>
""")

HTML_REGISTER = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
    <h2>Register a New Account</h2>
    <form method="POST">
        <div class="form-group">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required>
        </div>
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required>
        </div>
        <div class="form-group">
            <label for="full_name">Full Name / Company Name</label>
            <input type="text" id="full_name" name="full_name" required>
        </div>
        <div class="form-group">
            <label for="role">Register as:</label>
            <select id="role" name="role">
                <option value="patient">Patient</option>
                <option value="doctor">Doctor</option>
                <option value="insurance">Insurance</option>
            </select>
        </div>
        <button type="submit" class="btn">Register</button>
    </form>
""")

HTML_LOGIN = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
    <h2>Login</h2>
    <form method="POST">
        <div class="form-group">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required>
        </div>
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required>
        </div>
        <button type="submit" class="btn">Login</button>
    </form>
""")

HTML_PATIENT_DASH = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
    <h1>Patient Dashboard</h1>
    <p>Welcome, {{ current_user.email }}!</p>
    <p>Your name is: {{ current_user.patient_profile.full_name }}</p>
    
    <h2>Your Features:</h2>
    <ul>
        <li><b>Search for Doctors:</b> (Build your search logic here)</li>
        <li><b>View Medical Records:</b> (Query and display your records here)</li>
        <li><b>Book Appointments:</b> (Build your booking form here)</li>
    </ul>
""")

HTML_DOCTOR_DASH = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
    <h1>Doctor Dashboard</h1>
    <p>Welcome, {{ current_user.email }}!</p>
    <p>Your name is: {{ current_user.doctor_profile.full_name }}</p>

    <h2>Your Features:</h2>
    <ul>
        <li><b>View Your Appointments:</b> (Query and display appointments here)</li>
        <li><b>Update Patient Medical Records:</b> (Build your form to find patients and add records here)</li>
    </ul>
""")

HTML_INSURANCE_DASH = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
    <h1>Insurance Dashboard</h1>
    <p>Welcome, {{ current_user.email }}!</p>
    <p>Your company is: {{ current_user.insurance_profile.company_name }}</p>

    <h2>Your Features:</h2>
    <ul>
        <li><b>Insurance Recommendation Algorithm:</b> (Build your search/matching logic here for patients)</li>
    </ul>
""")


# --- General Routes ---

@app.route("/")
def home():
    """Renders the homepage."""
    return render_template_string(HTML_HOME)

@app.route("/register", methods=['GET', 'POST'])
def register():
    """Handles registration for all three user types."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        full_name = request.form.get('full_name')

        # Check if user already exists
        existing_user = db.session.scalar(db.select(User).where(User.email == email))
        if existing_user:
            flash('Email already registered. Please log in.', 'danger')
            return redirect(url_for('login'))

        # Hash the password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Create new user
        new_user = User(email=email, password_hash=hashed_password, role=role)
        db.session.add(new_user)
        
        # We must commit the user first to get its ID for the profile
        db.session.commit()

        # Create the specific profile based on the selected role
        if role == 'patient':
            profile = PatientProfile(full_name=full_name, user_id=new_user.id)
        elif role == 'doctor':
            profile = DoctorProfile(full_name=full_name, user_id=new_user.id)
        elif role == 'insurance':
            profile = InsuranceProfile(company_name=full_name, user_id=new_user.id)
        
        db.session.add(profile)
        db.session.commit()

        flash(f'Account created for {email} as a {role}. You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template_string(HTML_REGISTER)


@app.route("/login", methods=['GET', 'POST'])
def login():
    """Handles login for all users."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = db.session.scalar(db.select(User).where(User.email == email))

        # Check if user exists and password is correct
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            flash('Login successful!', 'success')
            # Redirect to the central dashboard, which will route them
            return redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')

    return render_template_string(HTML_LOGIN)

@app.route("/logout")
@login_required
def logout():
    """Logs the current user out."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- Role-Specific Dashboard Routes ---

@app.route("/dashboard")
@login_required
def dashboard():
    """
    Central hub. Redirects the logged-in user to their
    correct dashboard based on their role.
    """
    if current_user.role == 'patient':
        return redirect(url_for('patient_dashboard'))
    elif current_user.role == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    elif current_user.role == 'insurance':
        return redirect(url_for('insurance_dashboard'))
    else:
        return "Error: Unknown user role.", 403


@app.route("/patient_dashboard")
@login_required
@patient_required
def patient_dashboard():
    """Displays the patient's dashboard. Only accessible to patients."""
    return render_template_string(HTML_PATIENT_DASH)

@app.route("/doctor_dashboard")
@login_required
@doctor_required
def doctor_dashboard():
    """Displays the doctor's dashboard. Only accessible to doctors."""
    return render_template_string(HTML_DOCTOR_DASH)

@app.route("/insurance_dashboard")
@login_required
@insurance_required
def insurance_dashboard():
    """Displays the insurance dashboard. Only accessible to insurance users."""
    return render_template_string(HTML_INSURANCE_DASH)

# --- Error Handler ---
@app.errorhandler(403)
def forbidden(e):
    """Custom error page for 403 Forbidden."""
    error_html = HTML_LAYOUT.replace('{% block content %}{% endblock %}', """
        <h1>403 - Forbidden</h1>
        <p>You do not have permission to access this page.</p>
        <a href="{{ url_for('home') }}">Go to Homepage</a>
    """)
    return render_template_string(error_html), 403

# --- Run the App ---

if __name__ == '__main__':
    # Create the database and tables if they don't exist
    with app.app_context():
        db.create_all()
        print("Database tables created at site.db")
    
    app.run(debug=True)
