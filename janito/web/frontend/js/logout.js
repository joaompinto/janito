document.getElementById('sign-out').addEventListener('click', async () => {
    const response = await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
    if (response.ok) window.location.replace('/login');
});
