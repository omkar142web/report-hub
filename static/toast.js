
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icon = document.createElement('span');
    icon.className = 'icon';
    if (type === 'success') {
        icon.textContent = '✅';
    } else if (type === 'error') {
        icon.textContent = '❌';
    } else {
        icon.textContent = 'ℹ️';
    }

    const text = document.createElement('span');
    text.className = 'toast-text';   // ✅ ADD THIS
    text.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'close-btn';
    closeBtn.innerHTML = '&times;';
    closeBtn.onclick = () => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        toast.addEventListener('animationend', () => toast.remove());
    };

    toast.appendChild(icon);
    toast.appendChild(text);
    toast.appendChild(closeBtn);

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        toast.addEventListener('animationend', () => toast.remove());
    }, 5000);
}
