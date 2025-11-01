import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt
from functools import wraps
from sqlalchemy.sql import func
import datetime

# --- App Setup ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = 'a_very_secret_key_that_you_should_change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Extensions ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# --- Database Models ---

# Association table for patient-doctor permissions
patient_doctor_permissions = db.Table('patient_doctor_permissions',
    db.Column('patient_id', db.Integer, db.ForeignKey('patient_profile.id'), primary_key=True),
    db.Column('doctor_id', db.Integer, db.ForeignKey('doctor_profile.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    patient_profile = db.relationship('PatientProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    doctor_profile = db.relationship('DoctorProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    insurance_profile = db.relationship('InsuranceProfile', backref='user', uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"User('{self.email}', '{self.role}')"

class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default='Unnamed')
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    records = db.relationship('MedicalRecord', backref='patient', lazy='dynamic', foreign_keys='MedicalRecord.patient_id')
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic', foreign_keys='Appointment.patient_id')
    reviews = db.relationship('DoctorReview', backref='patient', lazy='dynamic', foreign_keys='DoctorReview.patient_id')
    
    # Many-to-Many relationship for permissions
    permitted_doctors = db.relationship('DoctorProfile', secondary=patient_doctor_permissions,
        back_populates='permitted_patients')

class DoctorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default='Dr. Unnamed')
    phone = db.Column(db.String(20))
    specialty = db.Column(db.String(100))
    practice_address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    records_written = db.relationship('MedicalRecord', backref='doctor', lazy='dynamic', foreign_keys='MedicalRecord.doctor_id')
    appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic', foreign_keys='Appointment.doctor_id')
    reviews = db.relationship('DoctorReview', backref='doctor_profile', lazy='dynamic', foreign_keys='DoctorReview.doctor_id')
    
    # Many-to-Many relationship for permissions
    permitted_patients = db.relationship('PatientProfile', secondary=patient_doctor_permissions,
        back_populates='permitted_doctors')

class InsuranceProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False, default='Unnamed Company')
    phone = db.Column(db.String(20))
    company_address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
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
    status = db.Column(db.String(20), nullable=False, default='Pending') # Pending, Confirmed, Cancelled, Completed
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)

class DoctorReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cost_rating = db.Column(db.Integer, nullable=False) # 1-10
    hospitality_rating = db.Column(db.Integer, nullable=False) # 1-10
    med_rec_rating = db.Column(db.Integer, nullable=False) # 1-10
    overall_rating = db.Column(db.Integer, nullable=False) # 1-10
    comment = db.Column(db.Text)
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)
    # Unique constraint to ensure one review per patient per doctor
    __table_args__ = (db.UniqueConstraint('patient_id', 'doctor_id', name='_patient_doctor_review_uc'),)


# --- Flask-Login Helper ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Role-Specific Decorators ---
def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role_name:
                abort(403)
            # Store the correct profile in the 'g' object for easy access in templates
            if current_user.role == 'patient':
                g.profile = current_user.patient_profile
            elif current_user.role == 'doctor':
                g.profile = current_user.doctor_profile
            elif current_user.role == 'insurance':
                g.profile = current_user.insurance_profile
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- General Routes ---
@app.route("/")
def home():
    return render_template('home.html')

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        pincode = request.form.get('pincode')
        
        existing_user = db.session.scalar(db.select(User).where(User.email == email))
        if existing_user:
            flash('Email already registered. Please log in.', 'danger')
            return redirect(url_for('login'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(email=email, password_hash=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit() # Commit to get new_user.id

        if role == 'patient':
            profile = PatientProfile(full_name=full_name, phone=phone, address=address, pincode=pincode, user_id=new_user.id)
        elif role == 'doctor':
            profile = DoctorProfile(full_name=full_name, phone=phone, practice_address=address, pincode=pincode, user_id=new_user.id, specialty=request.form.get('specialty', 'General'))
        elif role == 'insurance':
            profile = InsuranceProfile(company_name=full_name, phone=phone, company_address=address, pincode=pincode, user_id=new_user.id)
        
        if profile:
            db.session.add(profile)
            db.session.commit()
            flash(f'Account created for {email} as a {role}. You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Error creating profile.', 'danger')
            db.session.delete(new_user) # Rollback user creation
            db.session.commit()
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.session.scalar(db.select(User).where(User.email == email))
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- Dashboard Routes ---
@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == 'patient':
        return redirect(url_for('patient_dashboard'))
    elif current_user.role == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    elif current_user.role == 'insurance':
        return redirect(url_for('insurance_dashboard'))
    else:
        return "Error: Unknown user role.", 403

# --- Patient Routes ---
@app.route("/patient_dashboard")
@login_required
@role_required('patient')
def patient_dashboard():
    # Medical Record Timeline
    timeline = g.profile.records.order_by(MedicalRecord.created_at.desc()).all()
    
    # Get all doctors this patient has had an appointment with
    doctor_ids = {apt.doctor_id for apt in g.profile.appointments.all()}
    permissioned_doctors = {doc.id for doc in g.profile.permitted_doctors}
    
    doctors = db.session.scalars(db.select(DoctorProfile).where(DoctorProfile.id.in_(doctor_ids))).all()

    return render_template('patient_dashboard.html', timeline=timeline, doctors=doctors, permissioned_doctors=permissioned_doctors)

@app.route("/search_doctors", methods=['POST'])
@login_required
@role_required('patient')
def search_doctors():
    specialty = request.form.get('specialty')
    pincode = request.form.get('pincode')

    # Base query
    query = db.select(DoctorProfile)
    
    if specialty:
        query = query.where(DoctorProfile.specialty.ilike(f'%{specialty}%'))
    if pincode:
        query = query.where(DoctorProfile.pincode == pincode)

    # Subquery to calculate average ratings
    avg_ratings_subquery = db.select(
        DoctorReview.doctor_id,
        func.avg(DoctorReview.overall_rating).label('avg_overall'),
        func.avg(DoctorReview.cost_rating).label('avg_cost'),
        func.avg(DoctorReview.hospitality_rating).label('avg_hospitality')
    ).group_by(DoctorReview.doctor_id).subquery()
    
    # Join the doctor query with the ratings subquery
    query = query.join(avg_ratings_subquery, DoctorProfile.id == avg_ratings_subquery.c.doctor_id, isouter=True)
    # Add the average fields to the selection
    query = query.add_columns(
        avg_ratings_subquery.c.avg_overall,
        avg_ratings_subquery.c.avg_cost,
        avg_ratings_subquery.c.avg_hospitality
    )
    
    # Order by highest overall rating first
    results = db.session.execute(query.order_by(db.desc('avg_overall'))).all()
    
    # 'results' is a list of Row objects. Each row contains:
    # (DoctorProfile object, avg_overall, avg_cost, avg_hospitality)
    
    return render_template('search_results.html', results=results, specialty=specialty, pincode=pincode)


@app.route("/book_appointment/<int:doctor_id>", methods=['GET', 'POST'])
@login_required
@role_required('patient')
def book_appointment(doctor_id):
    doctor = db.session.get(DoctorProfile, doctor_id)
    if not doctor:
        flash('Doctor not found.', 'danger')
        return redirect(url_for('patient_dashboard'))

    if request.method == 'POST':
        try:
            apt_time_str = request.form.get('appointment_time')
            apt_time = datetime.datetime.fromisoformat(apt_time_str)
            
            # Check if appointment is in the past
            if apt_time < datetime.datetime.now():
                flash('Cannot book an appointment in the past.', 'danger')
                return render_template('book_appointment.html', doctor=doctor)

            new_apt = Appointment(
                appointment_time=apt_time,
                patient_id=g.profile.id,
                doctor_id=doctor.id,
                status='Pending'
            )
            db.session.add(new_apt)
            db.session.commit()
            flash(f'Appointment request sent to {doctor.full_name} for {apt_time.strftime("%Y-%m-%d %I:%M %p")}.', 'success')
            return redirect(url_for('patient_dashboard'))
        except ValueError:
            flash('Invalid date format.', 'danger')
    
    return render_template('book_appointment.html', doctor=doctor)

@app.route("/manage_permissions", methods=['POST'])
@login_required
@role_required('patient')
def manage_permissions():
    # Get the list of doctor IDs from the form
    selected_doctor_ids = request.form.getlist('doctor_ids', type=int)
    
    # Get all doctors this patient has seen
    all_seen_doctors_ids = {apt.doctor_id for apt in g.profile.appointments.all()}
    all_seen_doctors = db.session.scalars(db.select(DoctorProfile).where(DoctorProfile.id.in_(all_seen_doctors_ids))).all()
    
    # Update permissions
    g.profile.permitted_doctors.clear()
    for doc in all_seen_doctors:
        if doc.id in selected_doctor_ids:
            g.profile.permitted_doctors.append(doc)
            
    db.session.commit()
    flash('Permissions updated successfully.', 'success')
    return redirect(url_for('patient_dashboard'))


# --- Doctor Routes ---
@app.route("/doctor_dashboard")
@login_required
@role_required('doctor')
def doctor_dashboard():
    # Get all appointments for this doctor
    appointments = g.profile.appointments.order_by(Appointment.appointment_time.asc()).all()
    pending_apts = [a for a in appointments if a.status == 'Pending']
    confirmed_apts = [a for a in appointments if a.status == 'Confirmed']
    completed_apts = [a for a in appointments if a.status == 'Completed']
    
    return render_template('doctor_dashboard.html', 
                           pending_apts=pending_apts, 
                           confirmed_apts=confirmed_apts,
                           completed_apts=completed_apts)

@app.route("/appointment_action/<int:appointment_id>/<string:action>")
@login_required
@role_required('doctor')
def appointment_action(appointment_id, action):
    apt = db.session.get(Appointment, appointment_id)
    # Check if appointment exists and belongs to this doctor
    if not apt or apt.doctor_id != g.profile.id:
        flash('Appointment not found or not authorized.', 'danger')
        return redirect(url_for('doctor_dashboard'))

    if action == 'confirm':
        apt.status = 'Confirmed'
        flash(f'Appointment with {apt.patient.full_name} confirmed.', 'success')
    elif action == 'cancel':
        apt.status = 'Cancelled'
        flash(f'Appointment with {apt.patient.full_name} cancelled.', 'info')
    elif action == 'complete':
        apt.status = 'Completed'
        flash(f'Appointment with {apt.patient.full_name} marked as completed.', 'success')
    else:
        flash('Invalid action.', 'danger')

    db.session.commit()
    return redirect(url_for('doctor_dashboard'))

@app.route("/update_record/<int:patient_id>", methods=['GET', 'POST'])
@login_required
@role_required('doctor')
def update_record(patient_id):
    patient = db.session.get(PatientProfile, patient_id)
    if not patient:
        flash('Patient not found.', 'danger')
        return redirect(url_for('doctor_dashboard'))

    # Check for permission
    has_permission = patient in g.profile.permitted_patients
    
    if request.method == 'POST':
        # Doctor is "committing" a new record
        diagnosis = request.form.get('diagnosis')
        notes = request.form.get('notes')
        prescription = request.form.get('prescription')
        
        if not diagnosis:
            flash('Diagnosis is required.', 'danger')
        else:
            new_record = MedicalRecord(
                diagnosis=diagnosis,
                notes=notes,
                prescription=prescription,
                patient_id=patient.id,
                doctor_id=g.profile.id
            )
            db.session.add(new_record)
            db.session.commit()
            flash(f'New medical record added for {patient.full_name}.', 'success')
            return redirect(url_for('doctor_dashboard'))
    
    # Get patient's history
    if has_permission:
        # Doctor has permission, show all records
        timeline = patient.records.order_by(MedicalRecord.created_at.desc()).all()
    else:
        # No permission, show only records this doctor created
        timeline = patient.records.filter_by(doctor_id=g.profile.id).order_by(MedicalRecord.created_at.desc()).all()

    return render_template('update_record.html', patient=patient, timeline=timeline, has_permission=has_permission)


# --- Insurance Routes ---
@app.route("/insurance_dashboard")
@login_required
@role_required('insurance')
def insurance_dashboard():
    # Placeholder for insurance matching algorithm
    return render_template('insurance_dashboard.html')

# --- Error Handler ---
@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# --- Run the App ---
if __name__ == '__main__':
    # This check is no longer needed as init_db.py handles creation
    # with app.app_context():
    #     db.create_all()
    app.run(debug=True)

