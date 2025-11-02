import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, abort, g, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt
from functools import wraps
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import extract
import datetime
from geopy.distance import great_circle
from sqlalchemy import or_ # <-- IMPORT or_

# --- App Setup (Unchanged) ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = 'a_very_secret_key_that_you_should_change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Initialize Extensions (Unchanged) ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# --- Database Models (UPDATED) ---

# (Permissions Table Unchanged)
patient_doctor_permissions = db.Table('patient_doctor_permissions',
    db.Column('patient_id', db.Integer, db.ForeignKey('patient_profile.id'), primary_key=True),
    db.Column('doctor_id', db.Integer, db.ForeignKey('doctor_profile.id'), primary_key=True)
)

# (User Model Unchanged)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    patient_profile = db.relationship('PatientProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    doctor_profile = db.relationship('DoctorProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    insurance_profile = db.relationship('InsuranceProfile', backref='user', uselist=False, cascade="all, delete-orphan")

class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default='Unnamed')
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # --- NEW: Insurance Details for Patient ---
    insurance_policy_id = db.Column(db.String(100), nullable=True)
    insurance_company_id = db.Column(db.Integer, db.ForeignKey('insurance_profile.id'), nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    records = db.relationship('MedicalRecord', backref='patient', lazy='dynamic', foreign_keys='MedicalRecord.patient_id')
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic', foreign_keys='Appointment.patient_id')
    reviews = db.relationship('DoctorReview', backref='patient', lazy='dynamic', foreign_keys='DoctorReview.patient_id')
    files = db.relationship('MedicalFile', backref='patient', lazy='dynamic', foreign_keys='MedicalFile.patient_id')
    
    permitted_doctors = db.relationship('DoctorProfile', secondary=patient_doctor_permissions,
        back_populates='permitted_patients')
    
    # --- NEW: Relationship to their insurance company ---
    insurance_company = db.relationship('InsuranceProfile', foreign_keys=[insurance_company_id])


class DoctorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default='Dr. Unnamed')
    phone = db.Column(db.String(20))
    specialty = db.Column(db.String(100))
    practice_address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # --- NEW: Availability Fields ---
    availability_start_time = db.Column(db.Time) # e.g., 09:00:00
    availability_end_time = db.Column(db.Time)   # e.g., 17:00:00
    slot_duration_minutes = db.Column(db.Integer, default=30)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    records_written = db.relationship('MedicalRecord', backref='doctor', lazy='dynamic', foreign_keys='MedicalRecord.doctor_id')
    appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic', foreign_keys='Appointment.doctor_id')
    reviews = db.relationship('DoctorReview', backref='doctor_profile', lazy='dynamic', foreign_keys='DoctorReview.doctor_id')
    files_written = db.relationship('MedicalFile', backref='doctor', lazy='dynamic', foreign_keys='MedicalFile.doctor_id')
    
    permitted_patients = db.relationship('PatientProfile', secondary=patient_doctor_permissions,
        back_populates='permitted_doctors')

# (Other Models Unchanged)
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
    
    # --- NEW: Billing Fields ---
    bill_amount = db.Column(db.Float)
    bill_status = db.Column(db.String(20), nullable=False, default='Unbilled') # Unbilled, Unpaid, Paid, Pending Insurance
    bill_description = db.Column(db.Text)
    
    # --- NEW: Fields for Insurance Claim ---
    insurance_id = db.Column(db.Integer, db.ForeignKey('insurance_profile.id'), nullable=True)
    insurance_claim_status = db.Column(db.String(20), nullable=False, default='None') # None, Pending, Accepted, Rejected

    # Link to the insurance company
    insurance_company = db.relationship('InsuranceProfile', backref='claims', foreign_keys=[insurance_id])
    
    # --- NEW: Unique constraint for doctor and time ---
    # This ensures only one patient can book a specific slot with a doctor
    __table_args__ = (db.UniqueConstraint('doctor_id', 'appointment_time', name='_doctor_time_uc'),)


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

class MedicalFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), unique=True, nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)


# (Helpers, Decorators, General Routes Unchanged)
# ...
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

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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
            # --- NEW: Get optional insurance info ---
            policy_id = request.form.get('insurance_policy_id')
            company_id = request.form.get('insurance_company_id')
            profile = PatientProfile(
                full_name=full_name, 
                phone=phone, 
                address=address, 
                pincode=pincode, 
                user_id=new_user.id,
                insurance_policy_id=policy_id if policy_id else None,
                insurance_company_id=int(company_id) if company_id else None
            )
        elif role == 'doctor':
            # --- UPDATED: Set default availability ---
            profile = DoctorProfile(
                full_name=full_name, 
                phone=phone, 
                practice_address=address, 
                pincode=pincode, 
                user_id=new_user.id,
                specialty=request.form.get('specialty', 'General'),
                # --- NEW: Set default availability ---
                availability_start_time=datetime.time(9, 0),
                availability_end_time=datetime.time(17, 0),
                slot_duration_minutes=30
            )
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

    # --- NEW: Get insurance companies for dropdown ---
    insurance_companies = db.session.scalars(db.select(InsuranceProfile)).all()
    return render_template('register.html', insurance_companies=insurance_companies)


@app.route("/login", methods=['GET', 'POST'])
def login():
    # ... (This route is unchanged) ...
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
    # ... (This route is unchanged) ...
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route("/dashboard")
@login_required
def dashboard():
    # ... (This route is unchanged) ...
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
    # ... (This route logic is unchanged) ...
    records = g.profile.records.all()
    files = g.profile.files.all()
    timeline_items = sorted(records + files, key=lambda x: x.created_at, reverse=True)
    
    # --- UPDATED: Get all appointments for billing ---
    all_appointments = g.profile.appointments.order_by(Appointment.appointment_time.desc()).all()
    
    # --- Review logic now uses the `all_appointments` list ---
    completed_apts = [apt for apt in all_appointments if apt.status == 'Completed']
    reviewed_doctor_ids = {review.doctor_id for review in g.profile.reviews.all()}
    doctors_to_review = []
    seen_doctor_ids = set()
    for apt in completed_apts:
        if apt.doctor_id not in reviewed_doctor_ids and apt.doctor_id not in seen_doctor_ids:
            doctors_to_review.append(apt.doctor)
            seen_doctor_ids.add(apt.doctor_id)

    doctor_ids = {apt.doctor_id for apt in g.profile.appointments.all()}
    permissioned_doctors = {doc.id for doc in g.profile.permitted_doctors}
    doctors = db.session.scalars(db.select(DoctorProfile).where(DoctorProfile.id.in_(doctor_ids))).all()

    return render_template('patient_dashboard.html', 
                           timeline_items=timeline_items, 
                           doctors=doctors, 
                           permissioned_doctors=permissioned_doctors,
                           doctors_to_review=doctors_to_review,
                           appointments=all_appointments) # <-- Pass all appointments for billing

# --- NEW: Bill Payment Routes ---

@app.route("/pay_bill/<int:appointment_id>", methods=['GET'])
@login_required
@role_required('patient')
def pay_bill(appointment_id):
    apt = db.session.get(Appointment, appointment_id)
    if not apt:
        abort(404)
    if apt.patient_id != g.profile.id:
        abort(403) # Not this patient's bill
    if apt.bill_status != 'Unpaid':
        flash('This bill is not currently marked as unpaid.', 'info')
    if apt.bill_status not in ['Unpaid', 'Rejected']: # <-- Allow payment if Unpaid or Rejected
        flash('This bill is not currently marked as unpaid.', 'info')
        return redirect(url_for('patient_dashboard'))
    
    # --- REMOVED: No longer need to query all companies ---
    return render_template('pay_bill.html', apt=apt)

@app.route("/pay_upi/<int:appointment_id>")
@login_required
@role_required('patient')
def pay_upi(appointment_id):
    """Simulates a successful UPI payment."""
    apt = db.session.get(Appointment, appointment_id)
    if not apt:
        abort(404)
    if apt.patient_id != g.profile.id:
        abort(403)
    
    if apt.bill_status in ['Unpaid', 'Rejected']: # <-- Allow payment if Unpaid or Rejected
        apt.bill_status = 'Paid'
        db.session.commit()
        flash('Payment successful! Thank you.', 'success')
    else:
        flash('This bill is not currently marked as unpaid.', 'info')
        
    return redirect(url_for('patient_dashboard'))

@app.route("/claim_insurance/<int:appointment_id>", methods=['POST']) # <-- UPDATED to POST
@login_required
@role_required('patient')
def claim_insurance(appointment_id):
    """Submits a claim if the entered Policy ID matches the patient's file."""
    apt = db.session.get(Appointment, appointment_id)
    if not apt:
        abort(404)
    if apt.patient_id != g.profile.id:
        abort(403)
    
    # --- NEW: Validate against the patient's registered policy ID ---
    submitted_policy_id = request.form.get('insurance_policy_id')

    if not g.profile.insurance_policy_id or not g.profile.insurance_company_id:
        flash('You do not have an insurance policy registered on your profile.', 'danger')
        return redirect(url_for('pay_bill', appointment_id=appointment_id))
        
    if submitted_policy_id != g.profile.insurance_policy_id:
        flash('The Policy ID you entered does not match the ID on your profile.', 'danger')
        return redirect(url_for('pay_bill', appointment_id=appointment_id))
    # --- END NEW VALIDATION ---
    
    if apt.bill_status in ['Unpaid', 'Rejected']:
        apt.bill_status = 'Pending Insurance'
        apt.insurance_id = g.profile.insurance_company_id # <-- NEW: Link claim to patient's company
        apt.insurance_claim_status = 'Pending' # <-- NEW: Set claim status
        db.session.commit()
        flash(f'Bill claim submitted to {g.profile.insurance_company.company_name} for processing.', 'info')
    else:
        flash('This bill cannot be claimed at this time.', 'info')
        
    return redirect(url_for('patient_dashboard'))


# --- REFACTORED/FIXED SEARCH ROUTE ---
@app.route("/search_doctors", methods=['POST'])
@login_required
@role_required('patient')
def search_doctors():
    # --- FIXED: Get new form fields ---
    specialty = request.form.get('specialty')
    min_rating = int(request.form.get('min_rating', 1)) # Form default is 1
    sort_by = request.form.get('sort_by', 'default') # <-- FIXED: Default to 'default'
    # --- END FIX ---

    # Handle missing patient location
    patient_loc_missing = False # <-- FIX: Initialize variable
    patient_coords = None # <-- FIX: Initialize variable
    if not g.profile.latitude or not g.profile.longitude:
        flash('Please update your profile with a valid address to use the distance search. Distances are not available.', 'info')
        patient_loc_missing = True
    else:
        patient_coords = (g.profile.latitude, g.profile.longitude)

    avg_ratings_subquery = db.select(
        DoctorReview.doctor_id,
        func.avg(DoctorReview.overall_rating).label('avg_overall'),
        func.avg(DoctorReview.cost_rating).label('avg_cost'),
        func.avg(DoctorReview.hospitality_rating).label('avg_hospitality')
    ).group_by(DoctorReview.doctor_id).subquery()

    # --- SYNTAX FIX: Correctly structure the .select().join() ---
    query = db.select(
        DoctorProfile,
        avg_ratings_subquery.c.avg_overall,
        avg_ratings_subquery.c.avg_cost,
        avg_ratings_subquery.c.avg_hospitality
    ).join(
        avg_ratings_subquery,
        DoctorProfile.id == avg_ratings_subquery.c.doctor_id,
        isouter=True # This is a LEFT JOIN
    )
    # --- END SYNTAX FIX ---

    if specialty:
        query = query.where(DoctorProfile.specialty.ilike(f'%{specialty}%'))

    # --- FIXED: Handle min_rating to include NULLs (unrated) ---
    if min_rating > 1: # The form default is 1. Only filter if user selects 2 or more.
        query = query.where(
            or_(
                avg_ratings_subquery.c.avg_overall >= min_rating,
                avg_ratings_subquery.c.avg_overall == None # Always include unrated doctors
            )
        )
    # --- END FIX ---
    
    results = db.session.execute(query).all()
    
    final_results = []
    for row in results:
        doctor = row.DoctorProfile
        avg_overall = row.avg_overall
        avg_cost = row.avg_cost
        avg_hospitality = row.avg_hospitality
        
        distance_km = None
        if patient_coords and doctor.latitude and doctor.longitude:
            doctor_coords = (doctor.latitude, doctor.longitude)
            distance_km = great_circle(patient_coords, doctor_coords).km
        
        final_results.append((doctor, avg_overall, avg_cost, avg_hospitality, distance_km))
    
    # --- FIXED: Make sorting optional ---
    # 5. Sort the results in Python
    if sort_by == 'distance':
        if patient_loc_missing:
            # Fallback to sorting by rating
            final_results.sort(key=lambda x: (x[1] is None, x[1]), reverse=True)
        else:
            # Sort by distance (index 4), putting "None" distances at the end
            final_results.sort(key=lambda x: (x[4] is None, x[4]))
    elif sort_by == 'rating': # Make this an explicit check
        # Sort by rating (index 1), putting "None" ratings at the end
        final_results.sort(key=lambda x: (x[1] is None, x[1]), reverse=True)
    # else: (if sort_by is 'default') ... do nothing. The results will be in DB order.
    # --- END FIX ---

    return render_template('search_results.html', 
                           results=final_results, 
                           specialty=specialty, 
                           min_rating=min_rating,
                           sort_by=sort_by)

# --- NEW: Helper function to get available slots ---
def get_available_slots(doctor, selected_date):
    """
    Calculates the available appointment slots for a given doctor on a specific date.
    """
    if not doctor.availability_start_time or not doctor.availability_end_time or not doctor.slot_duration_minutes:
        return [] # Doctor has not set up their availability

    # Get all 'Pending' or 'Confirmed' appointments for this doctor on this day
    booked_appointments = db.session.scalars(
        db.select(Appointment)
        .where(
            Appointment.doctor_id == doctor.id,
            extract('year', Appointment.appointment_time) == selected_date.year,
            extract('month', Appointment.appointment_time) == selected_date.month,
            extract('day', Appointment.appointment_time) == selected_date.day,
            Appointment.status.in_(['Pending', 'Confirmed'])
        )
    ).all()
    
    # Create a set of booked datetimes for fast lookup
    booked_times = {apt.appointment_time for apt in booked_appointments}

    available_slots = []
    
    # Combine the selected date with the doctor's start time
    current_slot_time = datetime.datetime.combine(selected_date, doctor.availability_start_time)
    
    # Combine the selected date with the doctor's end time
    end_time = datetime.datetime.combine(selected_date, doctor.availability_end_time)
    
    slot_delta = datetime.timedelta(minutes=doctor.slot_duration_minutes)
    now = datetime.datetime.now()

    while current_slot_time < end_time:
        # Check if the slot is in the future and not in the booked set
        if current_slot_time > now and current_slot_time not in booked_times:
            available_slots.append(current_slot_time)
        
        current_slot_time += slot_delta

    return available_slots


# --- HEAVILY UPDATED BOOKING ROUTE ---
@app.route("/book_appointment/<int:doctor_id>", methods=['GET', 'POST'])
@login_required
@role_required('patient')
def book_appointment(doctor_id):
    doctor = db.session.get(DoctorProfile, doctor_id)
    if not doctor:
        flash('Doctor not found.', 'danger')
        return redirect(url_for('patient_dashboard'))

    # --- POST: Handle the booking submission ---
    if request.method == 'POST':
        try:
            apt_time_str = request.form.get('appointment_slot')
            apt_time = datetime.datetime.fromisoformat(apt_time_str)
            
            if apt_time < datetime.datetime.now():
                flash('Cannot book an appointment in the past.', 'danger')
                return redirect(url_for('book_appointment', doctor_id=doctor.id, date=apt_time.date().isoformat()))

            # --- NEW: Check if this *exact* slot is already taken ---
            # This is a critical check to prevent double-booking
            existing_apt = db.session.scalar(db.select(Appointment).where(
                Appointment.doctor_id == doctor.id,
                Appointment.appointment_time == apt_time,
                Appointment.status.in_(['Pending', 'Confirmed'])
            ))
            
            if existing_apt:
                flash(f'This slot ({apt_time.strftime("%I:%M %p")}) was just booked by someone else. Please select a different slot.', 'danger')
                return redirect(url_for('book_appointment', doctor_id=doctor.id, date=apt_time.date().isoformat()))
            # --- END NEW CHECK ---

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
            flash('Invalid slot selected.', 'danger')
        except Exception as e:
            db.session.rollback() # Rollback if the unique constraint fails
            flash(f'An error occurred. It\'s possible this slot was just booked. Please try again.', 'danger')
            return redirect(url_for('book_appointment', doctor_id=doctor_id))

    # --- GET: Show available slots for a given date ---
    selected_date_str = request.args.get('date')
    selected_date = None
    available_slots = []
    
    if selected_date_str:
        try:
            selected_date = datetime.date.fromisoformat(selected_date_str)
            if selected_date < datetime.date.today():
                flash('Cannot book appointments for past dates.', 'danger')
            else:
                available_slots = get_available_slots(doctor, selected_date)
        except ValueError:
            flash('Invalid date format.', 'danger')
    
    # --- NEW: Get today's date for the min attribute ---
    today_date = datetime.date.today().isoformat()
    
    # Fetch reviews for this doctor (unchanged)
    reviews = doctor.reviews.order_by(DoctorReview.created_at.desc()).all()
    
    return render_template('book_appointment.html', 
                           doctor=doctor, 
                           reviews=reviews,
                           selected_date=selected_date,
                           available_slots=available_slots,
                           today_date=today_date) # <-- Pass today's date to the template

# (Manage Permissions Route is Unchanged)
@app.route("/manage_permissions", methods=['POST'])
@login_required
@role_required('patient')
def manage_permissions():
    # ... (This route is unchanged) ...
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


# (Leave Review Route is Unchanged)
@app.route("/leave_review/<int:doctor_id>", methods=['GET', 'POST'])
@login_required
@role_required('patient')
def leave_review(doctor_id):
    # ... (This route is unchanged) ...
    doctor = db.session.get(DoctorProfile, doctor_id)
    if not doctor:
        flash('Doctor not found.', 'danger')
        return redirect(url_for('patient_dashboard'))

    had_completed_apt = db.session.scalar(db.select(Appointment).where(
        Appointment.patient_id == g.profile.id,
        Appointment.doctor_id == doctor.id,
        Appointment.status == 'Completed'
    ).limit(1))
    
    if not had_completed_apt:
        flash('You can only review doctors after a completed appointment.', 'danger')
        return redirect(url_for('patient_dashboard'))
        
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
@app.route("/doctor_dashboard")
@login_required
@role_required('doctor')
def doctor_dashboard():
    # ... (This route is unchanged) ...
    appointments = g.profile.appointments.order_by(Appointment.appointment_time.asc()).all()
    pending_apts = [a for a in appointments if a.status == 'Pending']
    confirmed_apts = [a for a in appointments if a.status == 'Confirmed']
    completed_apts = [a for a in appointments if a.status == 'Completed']
    
    return render_template('doctor_dashboard.html', 
                           pending_apts=pending_apts, 
                           confirmed_apts=confirmed_apts,
                           completed_apts=completed_apts)

# --- NEW: Route to manage availability ---
@app.route("/manage_availability", methods=['POST'])
@login_required
@role_required('doctor')
def manage_availability():
    try:
        start_time_str = request.form.get('start_time') # "HH:MM"
        end_time_str = request.form.get('end_time')   # "HH:MM"
        duration = int(request.form.get('slot_duration', 30))

        if not start_time_str or not end_time_str:
            flash('Start time and end time are required.', 'danger')
            return redirect(url_for('doctor_dashboard'))

        start_time = datetime.time.fromisoformat(start_time_str)
        end_time = datetime.time.fromisoformat(end_time_str)

        if start_time >= end_time:
            flash('Start time must be before end time.', 'danger')
            return redirect(url_for('doctor_dashboard'))
        
        if duration < 10:
            flash('Slot duration must be at least 10 minutes.', 'danger')
            duration = 10

        g.profile.availability_start_time = start_time
        g.profile.availability_end_time = end_time
        g.profile.slot_duration_minutes = duration
        
        db.session.commit()
        flash('Availability updated successfully.', 'success')

    except Exception as e:
        flash(f'Error updating availability: {e}', 'danger')
    
    return redirect(url_for('doctor_dashboard'))


# (Appointment Action Route is Unchanged)
@app.route("/appointment_action/<int:appointment_id>/<string:action>")
@login_required
@role_required('doctor')
def appointment_action(appointment_id, action):
    # ... (This route is unchanged) ...
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

# --- NEW: Route for setting a bill ---
@app.route("/set_bill/<int:appointment_id>", methods=['POST'])
@login_required
@role_required('doctor')
def set_bill(appointment_id):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.doctor_id != g.profile.id:
        flash('Appointment not found or not authorized.', 'danger')
        return redirect(url_for('doctor_dashboard'))
    
    if apt.status != 'Completed':
        flash('Can only bill for completed appointments.', 'danger')
        return redirect(url_for('doctor_dashboard'))
    
    try:
        amount = float(request.form.get('bill_amount'))
        description = request.form.get('bill_description', '')
        
        if amount <= 0:
            flash('Bill amount must be greater than zero.', 'danger')
            return redirect(url_for('doctor_dashboard'))

        apt.bill_amount = amount
        apt.bill_description = description
        apt.bill_status = 'Unpaid' # Set status to Unpaid
        db.session.commit()
        flash(f'Bill sent to {apt.patient.full_name} for ${amount:.2f}.', 'success')

    except ValueError:
        flash('Invalid bill amount.', 'danger')
    
    return redirect(url_for('doctor_dashboard'))

# --- NEW: Route for marking a bill as paid ---
@app.route("/bill_action/<int:appointment_id>/<string:action>")
@login_required
@role_required('doctor')
def bill_action(appointment_id, action):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.doctor_id != g.profile.id:
        flash('Appointment not found or not authorized.', 'danger')
        return redirect(url_for('doctor_dashboard'))

    if action == 'pay':
        if apt.bill_status in ['Unpaid', 'Pending Insurance']: # <-- Allow marking as paid even if pending
            apt.bill_status = 'Paid'
            db.session.commit()
            flash(f'Bill for {apt.patient.full_name} marked as paid.', 'success')
        else:
            flash('Bill is not in a state that can be marked as paid.', 'info')
    else:
        flash('Invalid action.', 'danger')

    return redirect(url_for('doctor_dashboard'))


# (Update Record Route is Unchanged)
@app.route("/update_record/<int:patient_id>", methods=['GET', 'POST'])
@login_required
@role_required('doctor')
def update_record(patient_id):
    # ... (This route is unchanged) ...
    patient = db.session.get(PatientProfile, patient_id)
    if not patient:
        flash('Patient not found.', 'danger')
        return redirect(url_for('doctor_dashboard'))

    has_permission = patient in g.profile.permitted_patients
    
    if request.method == 'POST':
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
    
    timeline_items = []
    if has_permission:
        records = patient.records.all()
        files = patient.files.all()
        timeline_items = sorted(records + files, key=lambda x: x.created_at, reverse=True)
    else:
        records = patient.records.filter_by(doctor_id=g.profile.id).all()
        files = patient.files.filter_by(doctor_id=g.profile.id).all()
        timeline_items = sorted(records + files, key=lambda x: x.created_at, reverse=True)

    return render_template('update_record.html', patient=patient, timeline_items=timeline_items, has_permission=has_permission)


# (Upload File Route is Unchanged)
@app.route('/upload_file/<int:patient_id>', methods=['POST'])
@login_required
@role_required('doctor')
def upload_file(patient_id):
    # ... (This route is unchanged) ...
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
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{ext}"
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
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


# (Get File Route is Unchanged, including the fix from before)
@app.route('/uploads/<path:filename>')
@login_required
def get_file(filename):
    """Securely serves an uploaded file."""
    
    if current_user.role == 'patient':
        g.profile = current_user.patient_profile
    elif current_user.role == 'doctor':
        g.profile = current_user.doctor_profile
    elif current_user.role == 'insurance':
        g.profile = current_user.insurance_profile
    
    medical_file = db.session.scalar(db.select(MedicalFile).where(MedicalFile.filename == filename))
    if not medical_file:
        abort(404)

    is_authorized = False
    if current_user.role == 'patient':
        if medical_file.patient_id == g.profile.id:
            is_authorized = True
    
    elif current_user.role == 'doctor':
        if medical_file.doctor_id == g.profile.id:
            is_authorized = True
        elif medical_file.patient in g.profile.permitted_patients:
            is_authorized = True
            
    if not is_authorized:
        abort(403)
        
    try:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            filename, 
            as_attachment=False,
            download_name=medical_file.original_filename
        )
    except FileNotFoundError:
        abort(404)

# --- Insurance Routes (UPDATED) ---
@app.route("/insurance_dashboard")
@login_required
@role_required('insurance')
def insurance_dashboard():
    # --- NEW: Find all claims submitted to this company ---
    pending_claims = db.session.scalars(
        db.select(Appointment).where(
            Appointment.insurance_id == g.profile.id,
            Appointment.insurance_claim_status == 'Pending'
        ).order_by(Appointment.appointment_time.asc())
    ).all()
    
    processed_claims = db.session.scalars(
        db.select(Appointment).where(
            Appointment.insurance_id == g.profile.id,
            Appointment.insurance_claim_status.in_(['Accepted', 'Rejected'])
        ).order_by(Appointment.appointment_time.desc())
    ).all()

    return render_template('insurance_dashboard.html',
                           pending_claims=pending_claims,
                           processed_claims=processed_claims)

# --- NEW: Route for insurance to process a claim ---
@app.route("/process_claim/<int:appointment_id>/<string:action>")
@login_required
@role_required('insurance')
def process_claim(appointment_id, action):
    apt = db.session.get(Appointment, appointment_id)
    if not apt or apt.insurance_id != g.profile.id:
        flash('Claim not found or not assigned to your company.', 'danger')
        return redirect(url_for('insurance_dashboard'))

    if apt.insurance_claim_status != 'Pending':
        flash('This claim has already been processed.', 'info')
        return redirect(url_for('insurance_dashboard'))

    if action == 'accept':
        apt.insurance_claim_status = 'Accepted'
        apt.bill_status = 'Paid' # Mark the bill as Paid
        db.session.commit()
        flash(f'Claim for {apt.patient.full_name} (Amount: ${apt.bill_amount:.2f}) has been ACCEPTED and marked as Paid.', 'success')
    elif action == 'reject':
        apt.insurance_claim_status = 'Rejected'
        apt.bill_status = 'Unpaid' # Mark the bill as Unpaid again so patient must pay
        db.session.commit()
        flash(f'Claim for {apt.patient.full_name} (Amount: ${apt.bill_amount:.2f}) has been REJECTED. Patient notified to pay.', 'danger')
    else:
        flash('Invalid action.', 'danger')

    return redirect(url_for('insurance_dashboard'))


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True)
