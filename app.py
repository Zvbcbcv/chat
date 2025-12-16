from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
from datetime import datetime
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS friends
                 (id INTEGER PRIMARY KEY, user_id INTEGER, friend_id INTEGER,
                  UNIQUE(user_id, friend_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY, sender_id INTEGER, receiver_id INTEGER,
                  message TEXT, timestamp TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_user_id(username):
    db = get_db()
    user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    db.close()
    return user['id'] if user else None

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                      (username, password))
            db.commit()
            db.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            db.close()
            return 'Username already exists'
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                         (username, password)).fetchone()
        db.close()
        
        if user:
            session['username'] = username
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        return 'Invalid credentials'
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    friends = db.execute('''SELECT u.username FROM users u
                           JOIN friends f ON u.id = f.friend_id
                           WHERE f.user_id = ?''', (session['user_id'],)).fetchall()
    db.close()
    
    return render_template('home.html', username=session['username'], friends=friends)

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if 'username' not in session:
        return jsonify({'success': False})
    
    friend_username = request.json['username']
    friend_id = get_user_id(friend_username)
    
    if not friend_id:
        return jsonify({'success': False, 'error': 'User not found'})
    
    db = get_db()
    try:
        db.execute('INSERT INTO friends (user_id, friend_id) VALUES (?, ?)',
                  (session['user_id'], friend_id))
        db.execute('INSERT INTO friends (user_id, friend_id) VALUES (?, ?)',
                  (friend_id, session['user_id']))
        db.commit()
        db.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        db.close()
        return jsonify({'success': False, 'error': 'Already friends'})

@app.route('/chat/<friend_username>')
def chat(friend_username):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    friend_id = get_user_id(friend_username)
    if not friend_id:
        return 'Friend not found'
    
    db = get_db()
    messages = db.execute('''SELECT u.username, m.message, m.timestamp
                            FROM messages m
                            JOIN users u ON m.sender_id = u.id
                            WHERE (m.sender_id = ? AND m.receiver_id = ?)
                               OR (m.sender_id = ? AND m.receiver_id = ?)
                            ORDER BY m.timestamp''',
                         (session['user_id'], friend_id, friend_id, session['user_id'])).fetchall()
    db.close()
    
    return render_template('chat.html', friend=friend_username, messages=messages)

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

@socketio.on('send_message')
def handle_message(data):
    message = data['message']
    room = data['room']
    sender = session['username']
    receiver = data['receiver']
    
    receiver_id = get_user_id(receiver)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    db = get_db()
    db.execute('INSERT INTO messages (sender_id, receiver_id, message, timestamp) VALUES (?, ?, ?, ?)',
              (session['user_id'], receiver_id, message, timestamp))
    db.commit()
    db.close()
    
    emit('receive_message', {
        'sender': sender,
        'message': message,
        'timestamp': timestamp
    }, room=room)

@socketio.on('typing')
def handle_typing(data):
    room = data['room']
    emit('user_typing', {'username': session['username']}, room=room, include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    room = data['room']
    emit('user_stop_typing', room=room, include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True)