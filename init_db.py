import os
from main import app, db, bcrypt, User, PatientProfile, DoctorProfile, InsuranceProfile, DoctorReview, Appointment, MedicalRecord, MedicalFile
from faker import Faker
import random
import datetime

fake = Faker()

SPECIALTIES = [
    'Cardiologist', 'Dermatologist', 'Neurologist', 'Pediatrician',
    'Oncologist', 'Orthopedist', 'General', 'Surgeon', 'Psychiatrist'
]

def clear_database():
    """Drops all tables and recreates them."""
    print("Dropping all tables...")
    db.drop_all()
    print("Creating all tables...")
    db.create_all()

def create_fake_data():
    """Populates the database with fake data."""
    print("Generating fake data...")
    
    # --- Create Doctors (10) ---
    doctors = []
    for _ in range(10):
        full_name = f"Dr. {fake.name()}"
        email = fake.email()
        password = 'password' # Use a simple password for all test users
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        user = User(email=email, password_hash=hashed_password, role='doctor')
        db.session.add(user)
        db.session.commit() # Commit to get user.id

        # --- UPDATED: Add availability info ---
        profile = DoctorProfile(
            full_name=full_name,
            phone=fake.phone_number(),
            specialty=random.choice(SPECIALTIES),
            practice_address=fake.address(),
            pincode=fake.zipcode()[:5],
            user_id=user.id,
            availability_start_time=datetime.time(9, 0),
            availability_end_time=datetime.time(17, 0),
            slot_duration_minutes=30
        )
        db.session.add(profile)
        doctors.append(profile)
    
    # --- Create Patients (20) ---
    patients = []
    for _ in range(20):
        full_name = fake.name()
        email = fake.email()
        password = 'password'
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        user = User(email=email, password_hash=hashed_password, role='patient')
        db.session.add(user)
        db.session.commit()

        profile = PatientProfile(
            full_name=full_name,
            phone=fake.phone_number(),
            address=fake.address(),
            pincode=fake.zipcode()[:5],
            user_id=user.id
        )
        db.session.add(profile)
        patients.append(profile)

    # --- Create Insurance Users (5) ---
    for _ in range(5):
        company_name = fake.company()
        email = fake.email()
        password = 'password'
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        user = User(email=email, password_hash=hashed_password, role='insurance')
        db.session.add(user)
        db.session.commit()

        profile = InsuranceProfile(
            company_name=company_name,
            phone=fake.phone_number(),
            company_address=fake.address(),
            pincode=fake.zipcode()[:5],
            user_id=user.id
        )
        db.session.add(profile)

    db.session.commit()
    print(f"Created {len(doctors)} doctors, {len(patients)} patients, and 5 insurance users.")

    # --- Create Fake Reviews (50 total) ---
    reviews_count = 0
    for _ in range(50):
        patient = random.choice(patients)
        doctor = random.choice(doctors)

        # Check if this review already exists
        existing = db.session.scalar(db.select(DoctorReview).where(
            DoctorReview.patient_id == patient.id,
            DoctorReview.doctor_id == doctor.id
        ))
        
        if not existing:
            review = DoctorReview(
                cost_rating=random.randint(1, 10),
                hospitality_rating=random.randint(1, 10),
                med_rec_rating=random.randint(1, 10),
                overall_rating=random.randint(1, 10),
                comment=fake.text(max_nb_chars=200),
                patient_id=patient.id,
                doctor_id=doctor.id
            )
            db.session.add(review)
            reviews_count += 1
            
    db.session.commit()
    print(f"Created {reviews_count} fake doctor reviews.")
    
    # Add one easy-to-test patient
    email = "patient@test.com"
    password = "password"
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    p_user = User(email=email, password_hash=hashed_password, role='patient')
    db.session.add(p_user)
    db.session.commit()
    p_profile = PatientProfile(full_name="Test Patient", phone="1234567890", address="123 Test St", pincode="10001", user_id=p_user.id)
    db.session.add(p_profile)
    
    # Add one easy-to-test doctor
    email = "doctor@test.com"
    password = "password"
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    d_user = User(email=email, password_hash=hashed_password, role='doctor')
    db.session.add(d_user)
    db.session.commit()
    d_profile = DoctorProfile(
        full_name="Dr. Test", 
        phone="9876543210", 
        specialty="Cardiologist", 
        practice_address="456 Test Ave", 
        pincode="10001", 
        user_id=d_user.id,
        availability_start_time=datetime.time(9, 0),
        availability_end_time=datetime.time(17, 0),
        slot_duration_minutes=30
    )
    db.session.add(d_profile)
    
    db.session.commit()
    
    # --- NEW: Add a completed appointment to test billing ---
    print("Adding test appointment for billing...")
    completed_apt = Appointment(
        appointment_time=datetime.datetime.now() - datetime.timedelta(days=2),
        status='Completed',
        patient_id=p_profile.id,
        doctor_id=d_profile.id,
        bill_amount=150.00,
        bill_status='Unpaid',
        bill_description='Standard Consultation'
    )
    db.session.add(completed_apt)
    db.session.commit()

    print("Added test patient (patient@test.com) and test doctor (doctor@test.com). Password for both is 'password'.")


if __name__ == "__main__":
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'site.db')
    
    if os.path.exists(db_path):
        response = input("Database 'site.db' already exists. \nDo you want to DELETE it and create a new one with fake data? (yes/no): ")
        if response.lower() == 'yes':
            with app.app_context():
                clear_database()
                create_fake_data()
            print("Database has been reset and populated.")
        else:
            print("Initialization cancelled. Using existing database.")
    else:
        with app.app_context():
            clear_database()
            create_fake_data()
        print("Database 'site.db' created and populated.")

