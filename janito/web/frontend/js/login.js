// Exchange a user-entered token for an HttpOnly browser session.
document.getElementById('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = document.getElementById('token');
    const error = document.getElementById('error');
    error.textContent = '';
    try {
        const response = await fetch('/auth/login', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: input.value }),
        });
        input.value = '';
        if (!response.ok) {
            error.textContent = 'Sign-in failed. Check the access token and try again.';
            return;
        }
        window.location.replace('/');
    } catch (err) {
        input.value = '';
        error.textContent = 'Cannot reach the server. Please try again.';
    }
});
