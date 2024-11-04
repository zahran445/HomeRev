from flask import Flask, render_template, redirect, url_for, request, flash, session
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
from db_setup import db, User, Project  # Ensure User and Project models are imported
import os
import random


app = Flask(__name__)

migrate = Migrate(app, db)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///your_database.db'  # Update your database URI as needed
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')  # Folder to store uploaded images
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit upload size to 16MB
db.init_app(app)

# Ensure the uploads directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Routes for user login and registration
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, password=password).first()

        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=username, email=email, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Signup successful! Redirecting to login...', 'success')
        return redirect(url_for('login'))  # Redirect to login after successful registration

    return render_template('reg.html')

# Route for home page
@app.route('/home')
def home():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))

    return render_template('home.html')

@app.route('/project/<int:project_id>')
def project_details(project_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))
    project = Project.query.get_or_404(project_id)
    return render_template('project_details.html', project=project)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# New route for Design Your Home functionality
@app.route('/design_your_home')
def design_your_home():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))
    
    projects = Project.query.all()  # Fetch all projects from the database
    random_projects = random.sample(projects, min(10, len(projects)))  # Get up to 10 random projects
    project_ids = [p.id for p in random_projects]  # Get the IDs of the random projects
    return render_template('design_home.html', projects=random_projects, project_ids=project_ids)

# Function to check if the uploaded file is allowed
ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}  # Only allow JPEG files

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get form fields
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')

        # Image upload handling
        if 'image' not in request.files:
            flash('No file part in request', 'danger')
            return redirect(request.url)

        file = request.files['image']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Save project details to the database
            new_project = Project(
                name=name,
                description=description,
                price=float(price),
                image_path=f'uploads/{filename}',  # Store relative path
                user_id=session['user_id']  # Associate with current user
            )
            db.session.add(new_project)
            db.session.commit()

            # Confirm addition and redirect
            flash('Project added successfully!', 'success')
            return redirect(url_for('home'))

        else:
            flash('Invalid file format. Only JPEG allowed.', 'danger')
            return redirect(request.url)

    return render_template('add_product.html')

# Database initialization
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Ensure all tables are created
    app.run(debug=True)
