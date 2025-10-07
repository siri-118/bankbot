# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'manager', 'employee' (or 'user')
    password_hash = db.Column(db.String(256), nullable=True)  # store hashed password in production
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

class LoginLog(db.Model):
    __tablename__ = 'login_logs'
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    kind = db.Column(db.String(20))    # admin/user/manager
    user = db.Column(db.String(80))
    success = db.Column(db.Boolean)
    ip = db.Column(db.String(45))
    meta = db.Column(db.Text, nullable=True)  # optional extra data (json string)

    def __repr__(self):
        return f"<LoginLog {self.user} {self.time} success={self.success}>"

class FAQ(db.Model):
    __tablename__ = 'faqs'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FAQ {self.id} q={self.question[:30]}>"

class QuestionLog(db.Model):
    """
    Optional: store every question a user asks your bot (or category),
    so you can aggregate chart data (counts by topic).
    """
    __tablename__ = 'question_logs'
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user = db.Column(db.String(80), nullable=True)
    question_text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(80), nullable=True)  # optional topic tag
    resolved = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<QuestionLog {self.id} user={self.user} cat={self.category}>"