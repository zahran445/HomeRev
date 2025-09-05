import random
import sys
import cv2
from flask import Flask, jsonify, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit, join_room, leave_room
from ai import classify_room, inpaint_room, segment_and_generate_prompt
from db_setup import db, User, Project, Review, ChatRoom, Message
import os
from datetime import datetime

app = Flask(__name__)

# SocketIO setup
socketio = SocketIO(app)

app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///builder_platform.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db.init_app(app)
migrate = Migrate(app, db)

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/ai', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Process the uploaded image
            image = cv2.imread(file_path)

            # Resize the image for processing
            image_resized = cv2.resize(image, (512, 512))  # Resizing for processing efficiency

            # Classify room type
            room_type = classify_room(file_path)

            # Segment the image and apply enhancements
            mask, prompt = segment_and_generate_prompt(image_resized, room_type)

            # Inpaint the image using the prompt
            redesigned_image_path = inpaint_room(image_resized, mask, prompt, filename)

            return render_template('upload.html', filename=redesigned_image_path)
    return render_template('result.html')

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

# Route for the "Design Your Home" functionality

@app.route('/design_your_home', methods=['GET', 'POST'])
def design_your_home():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))

    # Get room filter values from the form (if any)
    selected_rooms = request.form.getlist('rooms')  # List of selected room types from the checkbox
    
    # Query all projects, filter by selected room types if provided
    if selected_rooms:
        projects = Project.query.filter(Project.room_type.in_(selected_rooms)).all()
    else:
        projects = Project.query.all()

    # Get up to 10 random projects (or as many as available)
    random_projects = random.sample(projects, min(10, len(projects)))  # Fetch random projects
    project_ids = [p.id for p in random_projects]  # Get the IDs of the random projects
    
    return render_template('design_home.html', projects=random_projects, project_ids=project_ids)

# Route to log out
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=username, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()

        flash('Signup successful! Redirecting to login...', 'success')
        return redirect(url_for('login'))

    return render_template('reg.html')

@app.route('/home')
def home():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))
    return render_template('home.html')

@app.route('/project/<int:project_id>', methods=['GET'])
def project_details(project_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))
    
    current_user_id = session.get('user_id')
    project = Project.query.get_or_404(project_id)
    reviews = Review.query.filter_by(project_id=project_id).all()
    
    # Determine if the current user is the uploader
    

    if project.user_id == current_user_id:
        # Fetch all chat rooms related to this project where the current user is the uploader
        chats = ChatRoom.query.filter_by(project_id=project_id, uploader_id=current_user_id).all()
    else:
        # Non-uploaders only have access to their specific chat room with the uploader, if it exists
        chats = []

    # Render the project details template with the correct context
    return render_template('project_details.html', project=project, reviews=reviews, 
                           current_user_id=current_user_id, chats=chats)

@app.route('/submit_review/<int:project_id>', methods=['POST'])
def submit_review(project_id):
    if 'user_id' not in session:
        flash('Please log in to submit a review', 'danger')
        return redirect(url_for('login'))

    review_content = request.form.get('review_content')
    if not review_content:
        flash('Review cannot be empty', 'warning')
        return redirect(url_for('project_details', project_id=project_id))
    
    new_review = Review(content=review_content, project_id=project_id, user_id=session['user_id'])
    db.session.add(new_review)
    db.session.commit()

    flash('Your review has been submitted!', 'success')
    return redirect(url_for('project_details', project_id=project_id))
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        room_type = request.form.get('room_type')  # Get the room type from the form
        
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

            new_project = Project(
                name=name,
                description=description,
                price=float(price),
                image_path=f'uploads/{filename}',
                user_id=session['user_id'],
                room_type=room_type  # Save the room_type in the project
            )
            db.session.add(new_project)
            db.session.commit()

            flash('Project added successfully!', 'success')
            return redirect(url_for('home'))

        else:
            flash('Invalid file format. Only JPEG allowed.', 'danger')
            return redirect(request.url)

    return render_template('add_product.html')


@app.route('/chat_with_uploader/<int:project_id>', methods=['GET'])
def chat_with_uploader(project_id):
    """Route for users to initiate a chat with the uploader of a project."""
    if 'user_id' not in session:
        flash('Please log in to access the chat', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    project = Project.query.get(project_id)

    if not project:
        flash('Project not found', 'danger')
        return redirect(url_for('home'))

    uploader_id = project.user_id

    # Ensure the user is not the uploader
    if user_id == uploader_id:
        flash('You cannot chat with yourself on your own project.', 'danger')
        return redirect(url_for('home'))

    # Find or create a private chat room based on user_id and uploader_id
    chat_room = ChatRoom.find_or_create_private_room(project_id, user_id, uploader_id)
    messages = Message.query.filter_by(chat_room_id=chat_room.id).all()

    return render_template('chat.html', project=project, chat_room=chat_room, messages=messages, current_user_id=user_id)

@app.route('/uploader_chat/<int:project_id>/<int:chat_room_id>', methods=['GET'])
def uploader_chat(project_id, chat_room_id):
    """Route for uploaders to access existing chats with users for their project."""
    if 'user_id' not in session:
        flash('Please log in to access the chat', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    project = Project.query.get(project_id)

    if not project:
        flash('Project not found', 'danger')
        return redirect(url_for('home'))

    # Verify that the current user is the uploader
    if user_id != project.user_id:
        flash('You are not authorized to access this chat.', 'danger')
        return redirect(url_for('home'))

    # Retrieve the specific chat room if it exists
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, project_id=project_id).first()

    if not chat_room:
        flash('Chat room not found', 'danger')
        return redirect(url_for('home'))

    messages = Message.query.filter_by(chat_room_id=chat_room.id).all()
    return render_template('chat.html', project=project, chat_room=chat_room, messages=messages, current_user_id=user_id)

@socketio.on('join')
def handle_join(data):
    room = data['room']
    join_room(room)
    emit('status', {'msg': f"{data['username']} has joined the room."}, room=room)

@socketio.on('send_message')
def handle_send_message(data):
    room = data['room']
    username = data['username']
    message_content = data['message']
    
    # Debugging output to check room format and data
    print(f"Room identifier: {room}")
    print(f"Sender username: {username}")
    print(f"Message content: {message_content}")
    
    # Parse user_id and uploader_id from room string
    try:
        user_id, uploader_id = map(int, room.split("_"))
    except ValueError as e:
        print(f"Error parsing room identifier: {e}")
        return
    
    # Retrieve sender (User) and chat room (ChatRoom) from the database
    sender = User.query.filter_by(username=username).first()
    chat_room = ChatRoom.query.filter_by(user_id=user_id, uploader_id=uploader_id).first()
    
    # Debugging output to confirm fetched data
    print(f"Sender: {sender}")
    print(f"Chat Room: {chat_room}")

    if sender and chat_room:
        # Create and save new message to database
        new_message = Message(
            content=message_content,
            chat_room_id=chat_room.id,
            sender_id=sender.id,
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        # Emit the message to everyone in the room
        emit('receive_message', {
            'username': username,
            'message': message_content,
            'timestamp': new_message.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }, room=room)
    else:
        print("Error: Invalid sender or chat room.")

@app.route('/portfolio', methods=['GET', 'POST'])
def portfolio():
    user_id = session['user_id']
    user = User.query.filter_by(id=user_id).first()  # Replace with a valid user ID if not logged in
    projects = Project.query.filter_by(user_id=user.id).all()  # Assuming the user ID is 1 for demonstration

    if request.method == 'POST':
        # Handle profile updates (except username)
        if 'bio' in request.form:
            user.bio = request.form['bio']
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        return redirect(url_for('portfolio'))

    return render_template('portfolio.html', user=user, projects=projects)

# Route to delete a project
@app.route('/delete_project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    user_id = session['user_id']
    user = User.query.filter_by(id=user_id).first()  # Replace with valid user ID
    project = Project.query.get_or_404(project_id)

    # Ensure that the project belongs to the current user
    if project.user_id == user.id:
        db.session.delete(project)
        db.session.commit()
        flash('Project deleted successfully!', 'success')
    else:
        flash('You can only delete your own projects.', 'danger')

    return redirect(url_for('portfolio'))


# Route to view a user's profile without login requirement
@app.route('/profile/<int:user_id>')
def view_uploader_profile(user_id):
    # Retrieve the user by their ID
    user = User.query.get_or_404(user_id)
    
    # Retrieve all projects uploaded by this user
    projects = Project.query.filter_by(user_id=user.id).all()

    # Pass the user and their projects to the template
    return render_template('profile.html', user=user, projects=projects)

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)

