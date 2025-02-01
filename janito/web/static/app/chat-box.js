// Chat box setup and event handlers
export function setupChatBox(chatBoxContainer, onStateChange) {
    const chatBox = chatBoxContainer.querySelector('chat-box');
    if (!chatBox) return;

    // Add close handler for chat box
    chatBox.addEventListener('close', (event) => {
        // Get the editor container to check layout state
        const editorContainer = document.querySelector('.editor-container');
        const isEditorClosed = editorContainer.style.display === 'none';
        
        if (isEditorClosed) {
            // In two-column layout, hide chat box and show editor
            chatBoxContainer.style.display = 'none';
            editorContainer.style.display = 'flex';
            const nextSeparator = editorContainer.nextElementSibling;
            if (nextSeparator && nextSeparator.tagName.toLowerCase() === 'resizable-separator') {
                nextSeparator.style.display = 'block';
            }
            localStorage.setItem('editor-state', 'open');
        } else {
            // In three-column layout, just hide chat box
            chatBoxContainer.style.display = 'none';
        }
    });

    const commands = [
        { command: '/ask', description: 'Ask a question about the selected files' },
        { command: '/clear', description: 'Clear the chat history' },
        { command: '/help', description: 'Show available commands' },
        { command: '/run', description: 'Run selected Python files' },
        { command: '/search', description: 'Search in selected files' }
    ];

    // Command handlers
    async function handleCommand(command) {
        const cmd = command.split(' ')[0].toLowerCase();
        switch (cmd) {
            case '/clear':
                chatBox.clearMessages();
                chatBox.addMessage('assistant', 'Chat history cleared');
                break;
            case '/help':
                chatBox.addMessage('assistant', `Available commands:
/ask - Ask a question about the selected files
/clear - Clear the chat history
/help - Show this help message
/run - Run selected Python files
/search - Search in selected files`);
                break;
            default:
                chatBox.addMessage('assistant', `Unknown command: ${cmd}`);
        }
    }

    // Set up handlers
    chatBox.setHandlers({
        onInput: (text, cursorPosition) => {
            console.log('Chat input:', text, 'Cursor:', cursorPosition);
        },
        
        onSubmit: async (content) => {
            console.log('Chat submit handler called with:', content);
            if (content.startsWith('/')) {
                console.log('Handling command:', content);
                await handleCommand(content);
            } else {
                console.log('Emitting chat-message event with:', content);
                // Emit event for app-level handling
                const event = new CustomEvent('chat-message', {
                    bubbles: true,
                    detail: { content }
                });
                chatBoxContainer.dispatchEvent(event);
                console.log('chat-message event dispatched');
            }
        },

        getCommandSuggestions: (text) => {
            return commands.filter(cmd => 
                cmd.command.toLowerCase().startsWith(text.toLowerCase())
            );
        },

        getFileSuggestions: (searchText) => {
            const activeToggles = chatBox.getActiveToggles();
            return activeToggles
                .filter(path => path.toLowerCase().includes(searchText.toLowerCase()))
                .map(path => ({
                    path,
                    name: path.split('/').pop(),
                    icon: path.includes('.') ? '📄' : '📁'
                }));
        }
    });

    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if (e.key === 'F1' && e.altKey) {
            e.preventDefault();
            
            // Toggle visibility
            if (chatBoxContainer.style.display === 'none') {
                // Show chat box
                chatBoxContainer.style.display = 'flex';
                
                // If editor is closed, make sure chat box is expanded
                const editorContainer = document.querySelector('.editor-container');
                if (editorContainer.style.display === 'none') {
                    chatBoxContainer.classList.add('expanded');
                    chatBoxContainer.style.flex = '1';
                } else {
                    // Restore previous width in three-column layout
                    const savedWidth = localStorage.getItem('chatBoxContainer-width') || '300';
                    chatBoxContainer.style.width = `${savedWidth}px`;
                }
            } else {
                // Hide chat box
                chatBoxContainer.style.display = 'none';
                chatBoxContainer.classList.remove('expanded');
                chatBoxContainer.style.flex = '';
            }

            // Focus the chat input if showing
            if (chatBoxContainer.style.display !== 'none') {
                const chatInput = chatBox.shadowRoot.querySelector('.chat-input');
                if (chatInput) {
                    chatInput.focus();
                }
            }
        }
    });

    // Handle minimize/maximize
    chatBox.addEventListener('minimizeStateChange', (event) => {
        const isMinimized = event.detail.isMinimized;
        chatBoxContainer.classList.toggle('minimized', isMinimized);
        
        // Emit event for app-level handling
        chatBoxContainer.dispatchEvent(new CustomEvent('chatStateChange', {
            detail: { isMinimized }
        }));
        
        // Call the callback if provided
        if (onStateChange) {
            onStateChange(isMinimized);
        }
    });
} 