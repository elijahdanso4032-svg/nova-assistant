const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');

function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    const p = document.createElement('p');
    p.textContent = content;
    div.appendChild(p);
    chatWindow.appendChild(div);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    messageInput.disabled = true;

    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-msg assistant typing';
    typingDiv.innerHTML = '<p>...</p>';
    chatWindow.appendChild(typingDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    try {
        const res = await fetch('/api/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await res.json();
        typingDiv.remove();
        addMessage('assistant', data.reply || data.error || 'Something went wrong.');
    } catch (err) {
        typingDiv.remove();
        addMessage('assistant', 'Connection error — please try again.');
    }

    messageInput.disabled = false;
    messageInput.focus();
});

chatWindow.scrollTop = chatWindow.scrollHeight;
