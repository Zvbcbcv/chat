const socket = io();

const room = document.body.dataset.room;
const receiver = window.location.pathname.split('/').pop();
const currentUserId = parseInt(document.body.dataset.userId);

socket.emit('join', { room: room });

if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const messagesContainer = document.getElementById('messages');
const typingIndicator = document.getElementById('typing-indicator');

let typingTimeout;

sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

messageInput.addEventListener('input', () => {
    socket.emit('typing', { room: room });
    
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        socket.emit('stop_typing', { room: room });
    }, 1000);
});

function sendMessage() {
    const message = messageInput.value.trim();
    if (message) {
        socket.emit('send_message', {
            message: message,
            room: room,
            receiver: receiver
        });
        messageInput.value = '';
        socket.emit('stop_typing', { room: room });
    }
}

socket.on('receive_message', (data) => {
    const messageDiv = document.createElement('div');
    const currentUser = document.body.dataset.username;
    const isSent = data.sender === currentUser;
    
    messageDiv.className = `message ${isSent ? 'sent' : 'received'}`;
    messageDiv.innerHTML = `
        <div class="message-sender">${data.sender}</div>
        <div class="message-text">${data.message}</div>
        <div class="message-time">${data.timestamp}</div>
    `;
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    if (!isSent && document.hidden && Notification.permission === 'granted') {
        new Notification(`New message from ${data.sender}`, {
            body: data.message,
            icon: '/static/favicon.svg'
        });
    }
});

socket.on('new_message_notification', (data) => {
    if (data.receiver_id === currentUserId && data.sender !== document.body.dataset.username) {
        const currentChat = window.location.pathname.split('/').pop();
        if (currentChat !== data.sender) {
            showNotificationBar(data.sender, data.message);
        }
    }
});

function showNotificationBar(sender, message) {
    const notifBar = document.getElementById('notification-bar');
    const notifSender = document.getElementById('notif-sender');
    const notifMessage = document.getElementById('notif-message');
    
    notifSender.textContent = sender;
    notifMessage.textContent = message.length > 50 ? message.substring(0, 50) + '...' : message;
    
    notifBar.style.display = 'flex';
    
    setTimeout(() => {
        notifBar.style.display = 'none';
    }, 5000);
}

function dismissNotification() {
    document.getElementById('notification-bar').style.display = 'none';
}

socket.on('user_typing', (data) => {
    typingIndicator.textContent = `${data.username} is typing...`;
    typingIndicator.style.display = 'block';
});

socket.on('user_stop_typing', () => {
    typingIndicator.style.display = 'none';
});

messagesContainer.scrollTop = messagesContainer.scrollHeight;