import os
from  main import app, db, bcrypt, User, PatientProfile, DoctorProfile, InsuranceProfile, DoctorReview
from faker import Faker
import random

fake = Faker()

# Add this definition near the top
basedir = os.path.abspath(os.path.dirname(__file__))

# Specialties for doctors
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
    
    # --- Create Doctors (50) ---
    doctors = []
    for _ in range(50):
        full_name = f"Dr. {fake.name()}"
        email = fake.email()
        password = 'password' # Use a simple password for all test users
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        user = User(email=email, password_hash=hashed_password, role='doctor')
        db.session.add(user)
        db.session.commit() # Commit to get user.id

        profile = DoctorProfile(
            full_name=full_name,
            phone=fake.phone_number(),
            specialty=random.choice(SPECIALTIES),
            practice_address=fake.address(),
            pincode=fake.zipcode()[:5],
            user_id=user.id
        )
        db.session.add(profile)
        doctors.append(profile)
    
    # --- Create Patients (100) ---
    patients = []
    for _ in range(100):
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

    # --- Create Insurance Users (10) ---
    for _ in range(10):
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
    print(f"Created {len(doctors)} doctors, {len(patients)} patients, and 10 insurance users.")

    # --- Create Fake Reviews (1000) ---
    # Each patient reviews a random number of doctors
    reviews_count = 0
    for patient in patients:
        # Each patient reviews 5 to 15 doctors
        doctors_to_review = random.sample(doctors, random.randint(5, 15))
        for doctor in doctors_to_review:
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
    user = User(email=email, password_hash=hashed_password, role='patient')
    db.session.add(user)
    db.session.commit()
    profile = PatientProfile(full_name="Test Patient", phone="1234567890", address="123 Test St", pincode="10001", user_id=user.id)
    db.session.add(profile)
    
    # Add one easy-to-test doctor
    email = "doctor@test.com"
    password = "password"
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    user = User(email=email, password_hash=hashed_password, role='doctor')
    db.session.add(user)
    db.session.commit()
    profile = DoctorProfile(full_name="Dr. Test", phone="9876543210", specialty="Cardiologist", practice_address="456 Test Ave", pincode="10001", user_id=user.id)
    db.session.add(profile)
    
    db.session.commit()
    print("Added test patient (patient@test.com) and test doctor (doctor@test.com). Password for both is 'password'.")


if __name__ == "__main__":
    # Get the path to the database file
    db_path = os.path.join(basedir, 'site.db')
    
    # Check if the database file already exists
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
        # Database doesn't exist, create it
        with app.app_context():
            clear_database()
            create_fake_data()
        print("Database 'site.db' created and populated.")
