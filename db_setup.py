from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask import Flask
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, and_
# Create Flask app
app = Flask(__name__)

# Configure the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///builder_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the SQLAlchemy object
db = SQLAlchemy(app)

# Initialize Flask-Migrate
migrate = Migrate(app, db)
# Define IST timezone
IST = timezone(timedelta(hours=5, minutes=30))
# Get the current time in IST
def get_ist_time():
    return datetime.now(IST)

# Define your models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)  # New column for admin role

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Foreign key to User
    user = db.relationship('User', backref=db.backref('projects', lazy=True))
    reviews = db.relationship('Review', backref='project', lazy=True)
    room_type = db.Column(db.String(50), nullable=False)  # Type of room: Bedroom, Kitchen, etc.
    def __repr__(self):
        return f'<Project {self.name}>'


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Relationship to get user details
    user = db.relationship('User', backref='reviews', lazy=True)

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Initiating user
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Project owner
    is_private = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='room', lazy=True)

    user = db.relationship("User", foreign_keys=[user_id])
    def get_room_identifier(self):
        """Generate a unique room identifier for WebSocket communications"""
        if self.is_private:
            return f"private_{self.project_id}_{min(self.user_id, self.uploader_id)}_{max(self.user_id, self.uploader_id)}"
        return f"room_{self.id}"

    @staticmethod
    def find_or_create_private_room(project_id, user_id, uploader_id):
        """Find an existing chat room or create a new one."""
        # Check if a chat room already exists for this project and user/uploader pair
        chat_room = ChatRoom.query.filter_by(project_id=project_id, user_id=user_id, uploader_id=uploader_id).first()

        if not chat_room:
            # Create a new chat room if it doesn't exist
            chat_room = ChatRoom(project_id=project_id, user_id=user_id, uploader_id=uploader_id)
            db.session.add(chat_room)
            db.session.commit()

        return chat_room

    def __repr__(self):
        return f'<ChatRoom {self.name}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    chat_room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_system_message = db.Column(db.Boolean, default=False)
    read = db.Column(db.Boolean, default=False)
    sender = db.relationship('User', foreign_keys=[sender_id])

    def to_dict(self):
        sender = User.query.get(self.sender_id)
        return {
            'id': self.id,
            'content': self.content,
            'sender_id': self.sender_id,
            'sender_username': sender.username if not self.is_system_message else 'System',
            'timestamp': self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            'is_system_message': self.is_system_message,
            'read': self.read
        }

    @classmethod
    def mark_messages_as_read(cls, chat_room_id, user_id):
        """Mark all unread messages in a room as read for a user"""
        unread_messages = cls.query.filter_by(
            chat_room_id=chat_room_id,
            read=False
        ).filter(cls.sender_id != user_id).all()
        
        for message in unread_messages:
            message.read = True
        db.session.commit()

    def __repr__(self):
        return f'<Message {self.id} from {self.sender_id}>'