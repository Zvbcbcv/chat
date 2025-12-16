const socket = io();

const room = window.location.pathname.split('/').pop();
const receiver = room;

socket.emit('join', { room: room });

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
});

socket.on('user_typing', (data) => {
    typingIndicator.textContent = `${data.username} is typing...`;
    typingIndicator.style.display = 'block';
});

socket.on('user_stop_typing', () => {
    typingIndicator.style.display = 'none';
});

messagesContainer.scrollTop = messagesContainer.scrollHeight;