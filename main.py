import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, abort, g, send_from_directory
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

# --- File Upload Configuration ---
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf'}
# Create the upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# --- Initialize Extensions ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# --- Database Models ---

# (Patient-Doctor Permissions Table is unchanged)
patient_doctor_permissions = db.Table('patient_doctor_permissions',
    db.Column('patient_id', db.Integer, db.ForeignKey('patient_profile.id'), primary_key=True),
    db.Column('doctor_id', db.Integer, db.ForeignKey('doctor_profile.id'), primary_key=True)
)

# (User Model is unchanged)
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
    
    # NEW: Relationship to MedicalFile
    files = db.relationship('MedicalFile', backref='patient', lazy='dynamic', foreign_keys='MedicalFile.patient_id')
    
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
    
    # NEW: Relationship to MedicalFile
    files_written = db.relationship('MedicalFile', backref='doctor', lazy='dynamic', foreign_keys='MedicalFile.doctor_id')
    
    permitted_patients = db.relationship('PatientProfile', secondary=patient_doctor_permissions,
        back_populates='permitted_doctors')

# (InsuranceProfile Model is unchanged)
class InsuranceProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False, default='Unnamed Company')
    phone = db.Column(db.String(20))
    company_address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

# (MedicalRecord Model is unchanged)
class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    diagnosis = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    prescription = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)

# (Appointment Model is unchanged)
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending') # Pending, Confirmed, Cancelled, Completed
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)

# (DoctorReview Model is unchanged)
class DoctorReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cost_rating = db.Column(db.Integer, nullable=False) # 1-10
    hospitality_rating = db.Column(db.Integer, nullable=False) # 1-10
    med_rec_rating = db.Column(db.Integer, nullable=False) # 1-10
    overall_rating = db.Column(db.Integer, nullable=False) # 1-10
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('patient_id', 'doctor_id', name='_patient_doctor_review_uc'),)


# --- NEW MODEL ---
class MedicalFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # The secure, unique filename stored on the server (e.g., a UUID)
    filename = db.Column(db.String(256), unique=True, nullable=False)
    # The original filename the user uploaded (e.g., "lab_report.pdf")
    original_filename = db.Column(db.String(256), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)


# --- Flask-Login Helper & Role Decorators (Unchanged) ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role_name:
                abort(403)
            if current_user.role == 'patient':
                g.profile = current_user.patient_profile
            elif current_user.role == 'doctor':
                g.profile = current_user.doctor_profile
            elif current_user.role == 'insurance':
                g.profile = current_user.insurance_profile
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- File Upload Helper ---
def allowed_file(filename):
    """Checks if a filename has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- General Routes (Unchanged) ---
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
        db.session.commit()

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
            db.session.delete(new_user)
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

# --- Dashboard Route (Unchanged) ---
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

# --- Patient Routes (UPDATED) ---
@app.route("/patient_dashboard")
@login_required
@role_required('patient')
def patient_dashboard():
    # --- UPDATED: Combined Medical Timeline ---
    records = g.profile.records.all()
    files = g.profile.files.all()
    # Combine and sort records and files by creation date
    timeline_items = sorted(records + files, key=lambda x: x.created_at, reverse=True)
    
    # --- UPDATED: Logic for Pending Reviews ---
    # 1. Get all completed appointments
    completed_apts = g.profile.appointments.filter_by(status='Completed').all()
    # 2. Get IDs of doctors this patient has *already* reviewed
    reviewed_doctor_ids = {review.doctor_id for review in g.profile.reviews.all()}
    # 3. Find doctors from completed appointments that haven't been reviewed
    doctors_to_review = []
    seen_doctor_ids = set()
    for apt in completed_apts:
        if apt.doctor_id not in reviewed_doctor_ids and apt.doctor_id not in seen_doctor_ids:
            doctors_to_review.append(apt.doctor)
            seen_doctor_ids.add(apt.doctor_id)

    # (Permission Management Logic is Unchanged)
    doctor_ids = {apt.doctor_id for apt in g.profile.appointments.all()}
    permissioned_doctors = {doc.id for doc in g.profile.permitted_doctors}
    doctors = db.session.scalars(db.select(DoctorProfile).where(DoctorProfile.id.in_(doctor_ids))).all()

    return render_template('patient_dashboard.html', 
                           timeline_items=timeline_items, 
                           doctors=doctors, 
                           permissioned_doctors=permissioned_doctors,
                           doctors_to_review=doctors_to_review)

# (Search Doctors Route is Unchanged)
@app.route("/search_doctors", methods=['POST'])
@login_required
@role_required('patient')
def search_doctors():
    specialty = request.form.get('specialty')
    pincode = request.form.get('pincode')

    query = db.select(DoctorProfile)
    
    if specialty:
        query = query.where(DoctorProfile.specialty.ilike(f'%{specialty}%'))
    if pincode:
        query = query.where(DoctorProfile.pincode == pincode)

    avg_ratings_subquery = db.select(
        DoctorReview.doctor_id,
        func.avg(DoctorReview.overall_rating).label('avg_overall'),
        func.avg(DoctorReview.cost_rating).label('avg_cost'),
        func.avg(DoctorReview.hospitality_rating).label('avg_hospitality')
    ).group_by(DoctorReview.doctor_id).subquery()
    
    query = query.join(avg_ratings_subquery, DoctorProfile.id == avg_ratings_subquery.c.doctor_id, isouter=True)
    query = query.add_columns(
        avg_ratings_subquery.c.avg_overall,
        avg_ratings_subquery.c.avg_cost,
        avg_ratings_subquery.c.avg_hospitality
    )
    
    results = db.session.execute(query.order_by(db.desc('avg_overall'))).all()
    
    return render_template('search_results.html', results=results, specialty=specialty, pincode=pincode)

# (Book Appointment Route is Unchanged)
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

# (Manage Permissions Route is Unchanged)
@app.route("/manage_permissions", methods=['POST'])
@login_required
@role_required('patient')
def manage_permissions():
    selected_doctor_ids = request.form.getlist('doctor_ids', type=int)
    all_seen_doctors_ids = {apt.doctor_id for apt in g.profile.appointments.all()}
    all_seen_doctors = db.session.scalars(db.select(DoctorProfile).where(DoctorProfile.id.in_(all_seen_doctors_ids))).all()
    
    g.profile.permitted_doctors.clear()
    for doc in all_seen_doctors:
        if doc.id in selected_doctor_ids:
            g.profile.permitted_doctors.append(doc)
            
    db.session.commit()
    flash('Permissions updated successfully.', 'success')
    return redirect(url_for('patient_dashboard'))


# --- NEW ROUTE ---
@app.route("/leave_review/<int:doctor_id>", methods=['GET', 'POST'])
@login_required
@role_required('patient')
def leave_review(doctor_id):
    doctor = db.session.get(DoctorProfile, doctor_id)
    if not doctor:
        flash('Doctor not found.', 'danger')
        return redirect(url_for('patient_dashboard'))

    # Security: Check if patient had a completed appointment with this doctor
    had_completed_apt = db.session.scalar(db.select(Appointment).where(
        Appointment.patient_id == g.profile.id,
        Appointment.doctor_id == doctor.id,
        Appointment.status == 'Completed'
    ).limit(1))
    
    if not had_completed_apt:
        flash('You can only review doctors after a completed appointment.', 'danger')
        return redirect(url_for('patient_dashboard'))
        
    # Security: Check if patient already reviewed this doctor
    existing_review = db.session.scalar(db.select(DoctorReview).where(
        DoctorReview.patient_id == g.profile.id,
        DoctorReview.doctor_id == doctor.id
    ).limit(1))
    
    if existing_review:
        flash('You have already reviewed this doctor.', 'info')
        return redirect(url_for('patient_dashboard'))

    if request.method == 'POST':
        try:
            cost = int(request.form.get('cost_rating'))
            hospitality = int(request.form.get('hospitality_rating'))
            med_rec = int(request.form.get('med_rec_rating'))
            overall = int(request.form.get('overall_rating'))
            comment = request.form.get('comment')
            
            if not all(1 <= r <= 10 for r in [cost, hospitality, med_rec, overall]):
                raise ValueError("Ratings must be between 1 and 10.")

            new_review = DoctorReview(
                cost_rating=cost,
                hospitality_rating=hospitality,
                med_rec_rating=med_rec,
                overall_rating=overall,
                comment=comment,
                patient_id=g.profile.id,
                doctor_id=doctor.id
            )
            db.session.add(new_review)
            db.session.commit()
            flash('Thank you! Your review has been submitted.', 'success')
            return redirect(url_for('patient_dashboard'))
        except ValueError as e:
            flash(f'Invalid input. {e}', 'danger')
        
    return render_template('leave_review.html', doctor=doctor)


# --- Doctor Routes (UPDATED) ---

# (Doctor Dashboard Route is Unchanged)
@app.route("/doctor_dashboard")
@login_required
@role_required('doctor')
def doctor_dashboard():
    appointments = g.profile.appointments.order_by(Appointment.appointment_time.asc()).all()
    pending_apts = [a for a in appointments if a.status == 'Pending']
    confirmed_apts = [a for a in appointments if a.status == 'Confirmed']
    completed_apts = [a for a in appointments if a.status == 'Completed']
    
    return render_template('doctor_dashboard.html', 
                           pending_apts=pending_apts, 
                           confirmed_apts=confirmed_apts,
                           completed_apts=completed_apts)

# (Appointment Action Route is Unchanged)
@app.route("/appointment_action/<int:appointment_id>/<string:action>")
@login_required
@role_required('doctor')
def appointment_action(appointment_id, action):
    apt = db.session.get(Appointment, appointment_id)
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

# (Update Record Route is UPDATED)
@app.route("/update_record/<int:patient_id>", methods=['GET', 'POST'])
@login_required
@role_required('doctor')
def update_record(patient_id):
    patient = db.session.get(PatientProfile, patient_id)
    if not patient:
        flash('Patient not found.', 'danger')
        return redirect(url_for('doctor_dashboard'))

    has_permission = patient in g.profile.permitted_patients
    
    if request.method == 'POST':
        # This form is for "committing" a new text-based record
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
            return redirect(url_for('update_record', patient_id=patient.id))
    
    # --- UPDATED: Combined Timeline Logic ---
    timeline_items = []
    if has_permission:
        # Doctor has permission, show all records and files
        records = patient.records.all()
        files = patient.files.all()
        timeline_items = sorted(records + files, key=lambda x: x.created_at, reverse=True)
    else:
        # No permission, show only items this doctor created
        records = patient.records.filter_by(doctor_id=g.profile.id).all()
        files = patient.files.filter_by(doctor_id=g.profile.id).all()
        timeline_items = sorted(records + files, key=lambda x: x.created_at, reverse=True)

    return render_template('update_record.html', patient=patient, timeline_items=timeline_items, has_permission=has_permission)


# --- NEW ROUTE ---
@app.route('/upload_file/<int:patient_id>', methods=['POST'])
@login_required
@role_required('doctor')
def upload_file(patient_id):
    patient = db.session.get(PatientProfile, patient_id)
    if not patient:
        flash('Patient not found.', 'danger')
        return redirect(url_for('doctor_dashboard'))
    
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('update_record', patient_id=patient_id))
    
    file = request.files['file']
    description = request.form.get('description', '')

    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('update_record', patient_id=patient_id))

    if file and allowed_file(file.filename):
        from werkzeug.utils import secure_filename
        original_filename = secure_filename(file.filename)
        # Create a unique filename using UUID
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{ext}"
        
        # Save the file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        # Save to database
        new_file = MedicalFile(
            filename=unique_filename,
            original_filename=original_filename,
            description=description,
            patient_id=patient.id,
            doctor_id=g.profile.id
        )
        db.session.add(new_file)
        db.session.commit()
        
        flash('File uploaded successfully.', 'success')
    else:
        flash('File type not allowed. Allowed types are: png, jpg, jpeg, pdf.', 'danger')
        
    return redirect(url_for('update_record', patient_id=patient_id))


# --- NEW ROUTE ---
@app.route('/uploads/<path:filename>')
@login_required
def get_file(filename):
    """Securely serves an uploaded file."""
    
    # --- FIX: Manually set g.profile based on the logged-in user's role ---
    if current_user.role == 'patient':
        g.profile = current_user.patient_profile
    elif current_user.role == 'doctor':
        g.profile = current_user.doctor_profile
    elif current_user.role == 'insurance':
        g.profile = current_user.insurance_profile
    # --- END FIX ---
    
    # Find the file in the database
    medical_file = db.session.scalar(db.select(MedicalFile).where(MedicalFile.filename == filename))
    if not medical_file:
        abort(404) # Not Found

    # Security Check:
    is_authorized = False
    if current_user.role == 'patient':
        # Patients can only access their own files
        if medical_file.patient_id == g.profile.id:
            is_authorized = True
    
    elif current_user.role == 'doctor':
        # Doctors can access files they uploaded
        if medical_file.doctor_id == g.profile.id:
            is_authorized = True
        # Or files of patients who gave them permission
        elif medical_file.patient in g.profile.permitted_patients:
            is_authorized = True
            
    if not is_authorized:
        abort(403) # Forbidden
        
    # Serve the file
    # as_attachment=False tries to display in browser (e.g., PDFs, images)
    # download_name=... ensures it has the friendly, original filename
    try:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            filename, 
            as_attachment=False,
            download_name=medical_file.original_filename
        )
    except FileNotFoundError:
        abort(404)


# --- Insurance Routes (Unchanged) ---
@app.route("/insurance_dashboard")
@login_required
@role_required('insurance')
def insurance_dashboard():
    return render_template('insurance_dashboard.html')

# --- Error Handler (Unchanged) ---
@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True)
