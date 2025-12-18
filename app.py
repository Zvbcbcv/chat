from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import secrets
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS friends
                 (id SERIAL PRIMARY KEY, user_id INTEGER, friend_id INTEGER,
                  UNIQUE(user_id, friend_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id SERIAL PRIMARY KEY, sender_id INTEGER, receiver_id INTEGER,
                  message TEXT, timestamp TIMESTAMP, read BOOLEAN DEFAULT FALSE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (id SERIAL PRIMARY KEY, user1_id INTEGER, user2_id INTEGER,
                  last_message TEXT, last_timestamp TIMESTAMP,
                  UNIQUE(user1_id, user2_id))''')
    
    conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Database initialization error: {e}")

def get_user_id(username):
    conn = get_db()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute('SELECT id FROM users WHERE username = %s', (username,))
    user = c.fetchone()
    conn.close()
    return user['id'] if user else None

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

import base64

def load_banned_words():
    try:
        with open('banned.txt', 'r') as f:
            encoded = f.read().strip().split('\n')
            return [base64.b64decode(word).decode('utf-8') for word in encoded]
    except:
        return []

BANNED_WORDS = load_banned_words()

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        
        if any(banned in username for banned in BANNED_WORDS):
            error = 'Username contains inappropriate language'
            return render_template('register.html', error=error)
        
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password) VALUES (%s, %s)',
                      (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.close()
            error = 'Username already exists'
        except Exception as e:
            print(f"Register error: {e}")
            error = 'Registration failed'
    
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            conn = get_db()
            c = conn.cursor(cursor_factory=RealDictCursor)
            c.execute('SELECT * FROM users WHERE username = %s AND password = %s',
                     (username, password))
            user = c.fetchone()
            conn.close()
            
            if user:
                session['username'] = username
                session['user_id'] = user['id']
                return redirect(url_for('home'))
            error = 'Invalid username or password'
        except Exception as e:
            print(f"Login error: {e}")
            error = 'Invalid username or password'
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor(cursor_factory=RealDictCursor)
    
    c.execute('''SELECT u.id, u.username, 
                 MAX(m.message) as last_message, 
                 MAX(m.timestamp) as last_timestamp,
                 COUNT(CASE WHEN m.receiver_id = %s AND m.read = FALSE THEN 1 END) as unread_count
                 FROM messages m
                 JOIN users u ON (CASE WHEN m.sender_id = %s THEN m.receiver_id ELSE m.sender_id END) = u.id
                 WHERE m.sender_id = %s OR m.receiver_id = %s
                 GROUP BY u.id, u.username
                 ORDER BY MAX(m.timestamp) DESC''',
             (session['user_id'], session['user_id'], session['user_id'], session['user_id']))
    
    conversations = c.fetchall()
    
    c.execute('''SELECT u.username FROM users u
                 JOIN friends f ON u.id = f.friend_id
                 WHERE f.user_id = %s''', (session['user_id'],))
    friends = c.fetchall()
    
    conn.close()
    
    return render_template('home.html', username=session['username'], 
                          conversations=conversations, friends=friends)

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    friend_username = request.json['username'].strip().lower()
    friend_id = get_user_id(friend_username)
    
    if not friend_id:
        return jsonify({'success': False, 'error': 'User not found'})
    
    if friend_id == session['user_id']:
        return jsonify({'success': False, 'error': 'Cannot add yourself'})
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM friends WHERE user_id = %s AND friend_id = %s',
              (session['user_id'], friend_id))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Already friends'})
    
    try:
        c.execute('INSERT INTO friends (user_id, friend_id) VALUES (%s, %s)',
                  (session['user_id'], friend_id))
        c.execute('INSERT INTO friends (user_id, friend_id) VALUES (%s, %s)',
                  (friend_id, session['user_id']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        print(f"Add friend error: {e}")
        return jsonify({'success': False, 'error': 'Failed to add friend'})

@app.route('/chat/<friend_username>')
def chat(friend_username):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    friend_id = get_user_id(friend_username)
    if not friend_id:
        return 'Friend not found'
    
    user_ids = sorted([session['user_id'], friend_id])
    room = f"chat_{user_ids[0]}_{user_ids[1]}"
    
    conn = get_db()
    c = conn.cursor(cursor_factory=RealDictCursor)
    
    c.execute('''UPDATE messages SET read = TRUE 
                 WHERE receiver_id = %s AND sender_id = %s AND read = FALSE''',
             (session['user_id'], friend_id))
    conn.commit()
    
    c.execute('''SELECT u.username, m.message, m.timestamp
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE (m.sender_id = %s AND m.receiver_id = %s)
                   OR (m.sender_id = %s AND m.receiver_id = %s)
                ORDER BY m.timestamp''',
             (session['user_id'], friend_id, friend_id, session['user_id']))
    messages = c.fetchall()
    conn.close()
    
    return render_template('chat.html', friend=friend_username, messages=messages, room=room)

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    session.modified = True

@socketio.on('send_message')
def handle_message(data):
    message = data['message']
    room = data['room']
    sender = session['username']
    receiver = data['receiver']
    
    receiver_id = get_user_id(receiver)
    timestamp = datetime.now()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO messages (sender_id, receiver_id, message, timestamp) VALUES (%s, %s, %s, %s)',
              (session['user_id'], receiver_id, message, timestamp))
    conn.commit()
    conn.close()
    
    emit('receive_message', {
        'sender': sender,
        'message': message,
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
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