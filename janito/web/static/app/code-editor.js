// Code editor setup and event handlers
export function setupCodeEditor(codeEditor) {
    // Add file-selected event listener
    document.addEventListener('file-selected', (event) => {
        console.log('File selected event received:', event.detail);
        if (codeEditor) {
            codeEditor.setAttribute('file-extension', event.detail.fileExtension);
            codeEditor.setContent(event.detail.content);
            
            // Update language mode in status bar
            const languageMode = document.querySelector('.language-mode');
            if (languageMode) {
                const extension = event.detail.fileExtension;
                const language = extension.charAt(0).toUpperCase() + extension.slice(1);
                languageMode.textContent = `(${language})`;
            }
        }
    });
} 