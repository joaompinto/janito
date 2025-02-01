class ChatBox extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.itemStats = new Map(); // Store stats for each item
        this.commands = [
            { command: '/ask', description: 'Ask a question about the selected files' },
            { command: '/clear', description: 'Clear the chat history' },
            { command: '/help', description: 'Show available commands' },
            { command: '/run', description: 'Run selected Python files' },
            { command: '/search', description: 'Search in selected files' }
        ];
        this.previousWidth = 300; // Store default width
        this.activeToggles = new Set();
        this.handlers = {
            onInput: null,
            onSubmit: null,
            getCommandSuggestions: null,
            getFileSuggestions: null
        };
        this.isMinimized = false;
        this.setupChatBox();
    }

    setHandlers({
        onInput = null,
        onSubmit = null,
        getCommandSuggestions = null,
        getFileSuggestions = null
    }) {
        console.log('Setting chat box handlers');
        this.handlers = {
            onInput,
            onSubmit,
            getCommandSuggestions,
            getFileSuggestions
        };
    }

    setupChatBox() {
        const style = document.createElement('style');
        style.textContent = `
            :host {
                display: flex;
                height: 100%;
                width: 100%;
            }

            .chat-container {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                background-color: #252526;
            }

            :host(.minimized) {
                width: 48px;
            }

            :host(.minimized) .chat-container > *:not(.minimized-bar) {
                display: none;
            }

            .minimized-bar {
                display: none;
                flex-direction: column;
                align-items: center;
                width: 40px;
                height: 100%;
                background-color: #252526;
                border-left: 1px solid #3c3c3c;
            }

            :host(.minimized) .minimized-bar {
                display: flex;
            }

            .minimized-header {
                display: flex;
                justify-content: center;
                align-items: center;
                width: 100%;
                height: 40px;
                border-bottom: 1px solid #3c3c3c;
            }

            .restore-button {
                width: 100%;
                height: 100%;
                background: none;
                border: none;
                color: #bbbbbb;
                cursor: pointer;
                opacity: 0.8;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .restore-button:hover {
                opacity: 1;
                background-color: #2a2d2e;
            }

            .minimized-stats {
                display: flex;
                flex-direction: column;
                align-items: center;
                width: 100%;
                padding: 8px 0;
                color: #bbbbbb;
            }

            .minimized-stat-item {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 32px;
                gap: 2px;
            }

            .minimized-stat-item:hover {
                background-color: #2a2d2e;
            }

            .minimized-stat-item .icon {
                font-size: 14px;
            }

            .minimized-stat-item .value {
                font-size: 10px;
            }

            .chat-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 4px 8px;
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
                user-select: none;
            }

            .chat-header-title {
                font-size: 11px;
                text-transform: uppercase;
                font-weight: bold;
                color: #bbbbbb;
            }

            .chat-header-actions {
                display: flex;
                gap: 8px;
            }

            .chat-header-button {
                padding: 2px 4px;
                cursor: pointer;
                opacity: 0.8;
                background: none;
                border: none;
                color: #bbbbbb;
                font-size: 14px;
            }

            .chat-header-button:hover {
                opacity: 1;
            }

            .chat-messages {
                flex: 1;
                overflow-y: auto;
                padding: 8px;
                font-size: 13px;
            }

            .chat-input-area {
                display: flex;
                padding: 8px;
                gap: 8px;
                border-top: 1px solid #3c3c3c;
            }

            .chat-input {
                flex: 1;
                background-color: #3c3c3c;
                border: 1px solid #454545;
                border-radius: 3px;
                color: #d4d4d4;
                padding: 6px 8px;
                font-family: inherit;
                font-size: 13px;
                resize: none;
                min-height: 32px;
                max-height: 120px;
            }

            .chat-input:focus {
                outline: 1px solid #007acc;
            }

            .chat-send-button {
                background-color: #007acc;
                border: none;
                border-radius: 3px;
                color: white;
                padding: 0 12px;
                cursor: pointer;
                font-size: 13px;
            }

            .chat-send-button:hover {
                background-color: #1b8bd0;
            }

            .message {
                padding: 0;
                margin: 0;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                line-height: 1.2;
            }

            .message-content {
                font-size: 12px;
                white-space: pre-wrap;
                padding: 0 8px;
            }

            .message.user {
                background-color: rgba(128, 128, 128, 0.05);
                border-left: 2px solid #666666;
            }

            .message.assistant {
                background-color: rgba(0, 128, 255, 0.05);
                border-left: 2px solid #0088ff;
            }

            .message.system.error {
                background-color: rgba(255, 0, 0, 0.05);
                border-left: 2px solid #ff4444;
            }

            .message.system.status {
                background-color: rgba(128, 128, 128, 0.05);
                border-left: 2px solid #666666;
            }

            .message.system.info {
                background-color: rgba(0, 128, 255, 0.05);
                border-left: 2px solid #0088ff;
            }

            .file-toggles {
                display: flex;
                flex-direction: column;
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
            }

            .file-toggle {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                color: #bbbbbb;
                font-size: 12px;
                cursor: pointer;
                user-select: none;
                height: 24px;
                margin: 2px 0;
                max-width: calc(100% - 4px);
                min-height: 24px;
            }

            .file-toggle .name {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
                flex: 1;
            }

            .file-toggle.active {
                background-color: #37373d;
                border-color: #007acc;
                color: #ffffff;
            }

            .file-toggle:hover {
                background-color: #323232;
            }

            .file-toggle .close {
                margin-left: 4px;
                opacity: 0.6;
                font-size: 14px;
            }

            .file-toggle .close:hover {
                opacity: 1;
            }

            .file-toggle .icon {
                opacity: 0.8;
                font-size: 12px;
            }

            .file-toggles-content {
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                padding: 4px;
                max-height: calc(28px * 5);
                overflow-y: auto;
                overflow-x: hidden;
                
                /* Customize scrollbar */
                scrollbar-width: thin;
                scrollbar-color: #666 #252526;
            }

            /* Webkit scrollbar styles */
            .file-toggles-content::-webkit-scrollbar {
                width: 8px;
            }

            .file-toggles-content::-webkit-scrollbar-track {
                background: #252526;
            }

            .file-toggles-content::-webkit-scrollbar-thumb {
                background-color: #666;
                border-radius: 4px;
                border: 2px solid #252526;
            }

            .file-toggles-footer {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 4px 8px;
                border-top: 1px solid #3c3c3c;
                min-height: 24px;
            }

            .empty-toggles {
                color: #666;
                font-style: italic;
                font-size: 12px;
            }

            .clear-all-button {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 24px;
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                color: #bbbbbb;
                cursor: pointer;
                font-size: 14px;
                opacity: 0.8;
                margin: 2px 0;
            }

            .clear-all-button:hover {
                opacity: 1;
                color: #ff6b6b;
                background-color: #323232;
            }

            .file-stats {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 4px 8px;
                font-size: 12px;
                color: #8a8a8a;
                border-bottom: 1px solid #3c3c3c;
                background-color: #2d2d2d;
            }

            .stat-item {
                display: flex;
                align-items: center;
                gap: 4px;
            }

            .stat-item .icon {
                opacity: 0.7;
                font-size: 12px;
            }

            .command-suggestions {
                position: absolute;
                bottom: 100%;
                left: 0;
                right: 0;
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-bottom: none;
                max-height: 200px;
                overflow-y: auto;
                display: none;
            }

            .command-suggestions.show {
                display: block;
            }

            .command-suggestion {
                padding: 6px 12px;
                cursor: pointer;
                display: flex;
                justify-content: space-between;
                align-items: center;
                color: #d4d4d4;
            }

            .command-suggestion:hover,
            .command-suggestion.selected {
                background-color: #37373d;
            }

            .command-name {
                color: #569cd6;
                font-family: monospace;
            }

            .command-description {
                color: #808080;
                font-size: 12px;
                margin-left: 12px;
            }

            .chat-input-area {
                position: relative;
            }

            .file-suggestions {
                position: absolute;
                bottom: 100%;
                left: 0;
                right: 0;
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-bottom: none;
                max-height: 200px;
                overflow-y: auto;
                display: none;
            }

            .file-suggestions.show {
                display: block;
            }

            .file-suggestion {
                padding: 6px 12px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                color: #d4d4d4;
            }

            .file-suggestion:hover,
            .file-suggestion.selected {
                background-color: #37373d;
            }

            .file-suggestion .icon {
                opacity: 0.8;
            }

            .file-suggestion .path {
                color: #808080;
                font-size: 12px;
                margin-left: auto;
            }

            .file-toggles {
                position: relative;
            }

            .file-toggles.drag-over::after {
                content: 'Drop to add';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 122, 204, 0.1);
                border: 2px dashed #007acc;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 14px;
                color: #007acc;
                pointer-events: none;
            }
        `;

        const container = document.createElement('div');
        container.className = 'chat-container';
        container.innerHTML = `
            <div class="chat-header">
                <span class="chat-header-title">Chat Box</span>
                <div class="chat-header-actions">
                    <button class="chat-header-button minimize-button">−</button>
                    <button class="chat-header-button close-button">×</button>
                </div>
            </div>
            <div class="minimized-bar">
                <div class="minimized-header">
                    <button class="restore-button" title="Restore Chat Box">+</button>
                </div>
                <div class="minimized-stats">
                    <div class="minimized-stat-item">
                        <span class="icon">📑</span>
                        <span class="value total-items">0</span>
                    </div>
                    <div class="minimized-stat-item">
                        <span class="icon">📄</span>
                        <span class="value total-files">0</span>
                    </div>
                    <div class="minimized-stat-item">
                        <span class="icon">📁</span>
                        <span class="value total-folders">0</span>
                    </div>
                    <div class="minimized-stat-item">
                        <span class="icon">📊</span>
                        <span class="value total-size">0</span>
                    </div>
                </div>
            </div>
            <div class="file-toggles">
                <div class="file-toggles-content">
                    <div class="empty-toggles">No files or folders selected</div>
                </div>
                <div class="file-stats">
                    <div class="stat-item"><span class="icon">📑</span><span class="total-items">0 items</span></div>
                    <div class="stat-item"><span class="icon">📄</span><span class="total-files">0 files</span></div>
                    <div class="stat-item"><span class="icon">📁</span><span class="total-folders">0 folders</span></div>
                    <div class="stat-item"><span class="icon">📊</span><span class="total-size">0 KB</span></div>
                </div>
            </div>
            <div class="chat-messages"></div>
            <div class="chat-input-area">
                <textarea class="chat-input" placeholder="Type your message here..." rows="1"></textarea>
                <button class="chat-send-button">Send</button>
            </div>
        `;

        this.shadowRoot.appendChild(style);
        this.shadowRoot.appendChild(container);

        this.messagesContainer = this.shadowRoot.querySelector('.chat-messages');
        this.input = this.shadowRoot.querySelector('.chat-input');
        this.sendButton = this.shadowRoot.querySelector('.chat-send-button');
        this.minimizeButton = this.shadowRoot.querySelector('.minimize-button');
        this.closeButton = this.shadowRoot.querySelector('.close-button');
        this.fileTogglesContent = this.shadowRoot.querySelector('.file-toggles-content');
        this.emptyToggles = this.shadowRoot.querySelector('.empty-toggles');
        this.clearAllButton = this.shadowRoot.querySelector('.clear-all-button');

        this.setupEventListeners();
    }

    setupEventListeners() {
        this.input.addEventListener('keydown', (e) => {
            console.log('Chat input keydown:', e.key);
            const commandSuggestions = this.shadowRoot.querySelector('.command-suggestions');
            const fileSuggestions = this.shadowRoot.querySelector('.file-suggestions');
            
            if (commandSuggestions?.classList.contains('show')) {
                const selected = commandSuggestions.querySelector('.selected');
                switch (e.key) {
                    case 'ArrowDown':
                        e.preventDefault();
                        this.selectNextSuggestion(selected, commandSuggestions);
                        break;
                    case 'ArrowUp':
                        e.preventDefault();
                        this.selectPreviousSuggestion(selected, commandSuggestions);
                        break;
                    case 'Tab':
                    case 'Enter':
                        if (selected) {
                            e.preventDefault();
                            this.completeCommand(selected.querySelector('.command-name').textContent);
                        }
                        break;
                    case 'Escape':
                        e.preventDefault();
                        this.hideCommandSuggestions();
                        break;
                }
            } else if (fileSuggestions?.classList.contains('show')) {
                const selected = fileSuggestions.querySelector('.selected');
                switch (e.key) {
                    case 'ArrowDown':
                        e.preventDefault();
                        this.selectNextSuggestion(selected, fileSuggestions);
                        break;
                    case 'ArrowUp':
                        e.preventDefault();
                        this.selectPreviousSuggestion(selected, fileSuggestions);
                        break;
                    case 'Tab':
                    case 'Enter':
                        if (selected) {
                            e.preventDefault();
                            this.completeFileReference(selected.dataset.path);
                        }
                        break;
                    case 'Escape':
                        e.preventDefault();
                        this.hideFileSuggestions();
                        break;
                }
            } else if (e.key === 'Enter' && !e.shiftKey) {
                console.log('Enter pressed, sending message');
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.input.addEventListener('input', (e) => {
            // Auto-resize input
            this.input.style.height = 'auto';
            this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px';

            const text = this.input.value;
            const cursorPosition = this.input.selectionStart;
            
            // Get the text before the cursor
            const textBeforeCursor = text.substring(0, cursorPosition);
            
            if (this.handlers.onInput) {
                this.handlers.onInput(text, cursorPosition);
            }

            if (text.startsWith('/') && this.handlers.getCommandSuggestions) {
                const suggestions = this.handlers.getCommandSuggestions(text);
                this.showCommandSuggestions(suggestions);
            } else if (this.isTypingFileReference(textBeforeCursor) && this.handlers.getFileSuggestions) {
                const searchText = this.getFileSearchText(textBeforeCursor);
                const suggestions = this.handlers.getFileSuggestions(searchText);
                this.showFileSuggestions(suggestions);
            } else {
                this.hideCommandSuggestions();
                this.hideFileSuggestions();
            }
        });

        this.sendButton.addEventListener('click', () => {
            this.sendMessage();
        });

        this.minimizeButton.addEventListener('click', () => {
            this.minimize();
        });

        this.closeButton.addEventListener('click', () => {
            this.close();
        });

        const restoreButton = this.shadowRoot.querySelector('.restore-button');
        restoreButton.addEventListener('click', () => {
            this.restore();
        });

        // Add drop zone event listeners
        const fileToggles = this.shadowRoot.querySelector('.file-toggles');
        
        fileToggles.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            fileToggles.classList.add('drag-over');
            e.dataTransfer.dropEffect = 'copy';
        });

        fileToggles.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            fileToggles.classList.remove('drag-over');
        });

        fileToggles.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            fileToggles.classList.remove('drag-over');

            // Emit drop event for app-level handling
            const dropEvent = new CustomEvent('chatbox-drop', {
                bubbles: true,
                composed: true,
                detail: { 
                    path: e.dataTransfer.getData('text/plain')
                }
            });
            this.dispatchEvent(dropEvent);
        });
    }

    sendMessage() {
        const content = this.input.value.trim();
        console.log('sendMessage called with content:', content);
        if (!content) return;

        // Add user message to chat
        this.addMessage('user', content);

        // Process the message
        if (this.handlers.onSubmit) {
            console.log('Calling onSubmit handler');
            this.handlers.onSubmit(content);
        }

        // Clear input
        this.input.value = '';
        this.input.style.height = 'auto';
    }

    addMessage(type, content) {
        const message = document.createElement('div');
        message.className = `message ${type}`;
        message.innerHTML = `
            <div class="message-content">${content}</div>
        `;
        this.messagesContainer.appendChild(message);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    // New method for system messages
    addSystemMessage(content, type = 'info') {
        const message = document.createElement('div');
        message.className = `message system ${type}`;
        message.innerHTML = `
            <div class="message-content system-message">${content}</div>
        `;
        this.messagesContainer.appendChild(message);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    minimize() {
        this.isMinimized = true;
        this.classList.add('minimized');
        // Emit event for app-level handling
        this.dispatchEvent(new CustomEvent('minimizeStateChange', {
            bubbles: true,  // Allow event to bubble up to container
            detail: { isMinimized: true }
        }));
    }

    maximize() {
        this.isMinimized = false;
        this.classList.remove('minimized');
        // Emit event for app-level handling
        this.dispatchEvent(new CustomEvent('minimizeStateChange', {
            bubbles: true,  // Allow event to bubble up to container
            detail: { isMinimized: false }
        }));
    }

    restore() {
        this.classList.remove('minimized');
        this.isMinimized = false;
        
        // Emit event for app-level handling
        this.dispatchEvent(new CustomEvent('minimizeStateChange', {
            bubbles: true,
            detail: { isMinimized: false }
        }));
    }

    close() {
        this.dispatchEvent(new CustomEvent('close'));
    }

    clearAllToggles() {
        const toggles = this.fileTogglesContent.querySelectorAll('.file-toggle');
        toggles.forEach(toggle => toggle.remove());
        this.activeToggles.clear();
        this.itemStats.clear();
        this.emptyToggles.style.display = 'block';
        if (this.clearAllButton) {
            this.clearAllButton.remove();
        }
        this.dispatchEvent(new CustomEvent('toggles-cleared'));
        this.updateTotalStats();
    }

    async addFileToggle(path, type = 'file', recursive = false) {
        console.log(`Adding file toggle - Path: ${path}, Type: ${type}, Recursive: ${recursive}`);
        const togglesContainer = this.shadowRoot.querySelector('.file-toggles-content');
        this.emptyToggles.style.display = 'none';

        // Check if toggle already exists
        const existingToggle = togglesContainer.querySelector(`[data-path="${path}"]`);
        if (existingToggle) {
            console.log(`Toggle already exists for path: ${path}`);
            existingToggle.classList.add('active');
            this.activeToggles.add(path);
            this.updateTotalStats();
            return;
        }

        // Fetch stats for this item before creating the toggle
        try {
            console.log(`Fetching stats for path: ${path}`);
            const response = await fetch('http://localhost:8000/api/files/stats', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    paths: [path],
                    recursive: recursive
                })
            });

            if (!response.ok) throw new Error('Failed to fetch stats');
            const stats = await response.json();
            console.log(`Received stats for ${path}:`, stats);
            
            // Store stats with recursive flag
            this.itemStats.set(path, {
                ...stats,
                recursive: recursive
            });

            // Create and add the toggle
            const toggle = document.createElement('div');
            toggle.className = 'file-toggle active';
            toggle.dataset.path = path;
            toggle.dataset.recursive = recursive.toString();
            
            const folderIcon = recursive ? '🔄' : '📁';
            const icon = type === 'file' ? '📄' : folderIcon;
            const name = path.split('/').pop();
            
            toggle.innerHTML = `
                <span class="icon">${icon}</span>
                <span class="name">${name}</span>
                <span class="close">×</span>
            `;

            togglesContainer.appendChild(toggle);
            this.activeToggles.add(path);

            // Add or move clear all button
            if (!this.clearAllButton) {
                this.clearAllButton = document.createElement('button');
                this.clearAllButton.className = 'clear-all-button';
                this.clearAllButton.title = 'Clear all items';
                this.clearAllButton.textContent = '×';
                this.clearAllButton.addEventListener('click', () => this.clearAllToggles());
                togglesContainer.appendChild(this.clearAllButton);
            } else {
                togglesContainer.appendChild(this.clearAllButton);
            }

            // Update toggle event listener to handle recursive state
            toggle.addEventListener('click', (e) => {
                if (!e.target.classList.contains('close')) {
                    toggle.classList.toggle('active');
                    if (toggle.classList.contains('active')) {
                        console.log(`Activating toggle for ${path}`);
                        this.activeToggles.add(path);
                    } else {
                        console.log(`Deactivating toggle for ${path}`);
                        this.activeToggles.delete(path);
                    }
                    this.updateTotalStats();
                    this.dispatchEvent(new CustomEvent('toggle-change', {
                        detail: { 
                            path, 
                            active: toggle.classList.contains('active'),
                            recursive: toggle.dataset.recursive === 'true'
                        }
                    }));
                }
            });

            toggle.querySelector('.close').addEventListener('click', (e) => {
                e.stopPropagation();
                this.removeFileToggle(path);
            });

            console.log('Updating stats after adding toggle');
            this.updateTotalStats();

        } catch (error) {
            console.error('Error fetching item stats:', error);
        }
    }

    removeFileToggle(path) {
        const toggle = this.shadowRoot.querySelector(`[data-path="${path}"]`);
        if (toggle) {
            toggle.remove();
            this.activeToggles.delete(path);
            this.itemStats.delete(path);
            this.dispatchEvent(new CustomEvent('toggle-removed', {
                detail: { path }
            }));
        }

        if (this.activeToggles.size === 0) {
            this.emptyToggles.style.display = 'block';
            if (this.clearAllButton) {
                this.clearAllButton.remove();
            }
        }

        this.updateTotalStats();
    }

    getActiveToggles() {
        return Array.from(this.activeToggles);
    }

    updateTotalStats() {
        console.log('Updating total stats');
        console.log('Active toggles:', Array.from(this.activeToggles));
        console.log('Item stats:', Array.from(this.itemStats.entries()));

        const totalStats = {
            total_items: this.activeToggles.size,
            total_files: 0,
            total_folders: 0,
            total_size: 0
        };

        // Only count stats for active toggles
        for (const path of this.activeToggles) {
            const stats = this.itemStats.get(path);
            console.log(`Processing stats for ${path}:`, stats);
            if (stats) {
                // Use the stored stats which already account for recursive/non-recursive
                totalStats.total_files += stats.total_files;
                totalStats.total_folders += stats.total_folders;
                totalStats.total_size += stats.total_size;
            }
        }

        console.log('Final total stats:', totalStats);
        this.updateStatsDisplay(totalStats);
    }

    updateStatsDisplay(stats) {
        console.log('Updating stats display with:', stats);
        const formatSize = (bytes) => {
            if (bytes === 0) return '0';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))}${sizes[i]}`;
        };

        // Update stats in file-stats section
        const fileStats = this.shadowRoot.querySelector('.file-stats');
        if (fileStats) {
            const items = fileStats.querySelector('.total-items');
            const files = fileStats.querySelector('.total-files');
            const folders = fileStats.querySelector('.total-folders');
            const size = fileStats.querySelector('.total-size');

            if (items) items.textContent = `${stats.total_items} items`;
            if (files) files.textContent = `${stats.total_files} files`;
            if (folders) folders.textContent = `${stats.total_folders} folders`;
            if (size) size.textContent = formatSize(stats.total_size);
        }

        // Update minimized stats
        const minimizedStats = this.shadowRoot.querySelector('.minimized-stats');
        if (minimizedStats) {
            const items = minimizedStats.querySelector('.total-items');
            const files = minimizedStats.querySelector('.total-files');
            const folders = minimizedStats.querySelector('.total-folders');
            const size = minimizedStats.querySelector('.total-size');

            if (items) items.textContent = stats.total_items;
            if (files) files.textContent = stats.total_files;
            if (folders) folders.textContent = stats.total_folders;
            if (size) size.textContent = formatSize(stats.total_size);
        }

        console.log('Stats display updated');
    }

    showCommandSuggestions(suggestions) {
        const inputArea = this.shadowRoot.querySelector('.chat-input-area');
        let suggestionsEl = inputArea.querySelector('.command-suggestions');
        
        if (!suggestionsEl) {
            suggestionsEl = document.createElement('div');
            suggestionsEl.className = 'command-suggestions';
            inputArea.insertBefore(suggestionsEl, this.input);
        }

        if (suggestions.length > 0) {
            suggestionsEl.innerHTML = suggestions.map(suggestion => `
                <div class="command-suggestion">
                    <span class="command-name">${suggestion.command}</span>
                    <span class="command-description">${suggestion.description}</span>
                </div>
            `).join('');
            suggestionsEl.classList.add('show');

            suggestionsEl.querySelectorAll('.command-suggestion').forEach(el => {
                el.addEventListener('click', () => {
                    this.completeCommand(el.querySelector('.command-name').textContent);
                });
            });
        } else {
            this.hideCommandSuggestions();
        }
    }

    hideCommandSuggestions() {
        const suggestions = this.shadowRoot.querySelector('.command-suggestions');
        if (suggestions) {
            suggestions.classList.remove('show');
        }
    }

    selectNextSuggestion(selected, suggestions) {
        if (!selected) {
            suggestions.querySelector('.command-suggestion')?.classList.add('selected');
        } else {
            selected.classList.remove('selected');
            const next = selected.nextElementSibling;
            if (next) {
                next.classList.add('selected');
            } else {
                suggestions.querySelector('.command-suggestion')?.classList.add('selected');
            }
        }
    }

    selectPreviousSuggestion(selected, suggestions) {
        if (!selected) {
            const items = suggestions.querySelectorAll('.command-suggestion');
            items[items.length - 1]?.classList.add('selected');
        } else {
            selected.classList.remove('selected');
            const prev = selected.previousElementSibling;
            if (prev) {
                prev.classList.add('selected');
            } else {
                const items = suggestions.querySelectorAll('.command-suggestion');
                items[items.length - 1]?.classList.add('selected');
            }
        }
    }

    completeCommand(command) {
        this.input.value = command + ' ';
        this.input.focus();
        this.hideCommandSuggestions();
    }

    isTypingFileReference(text) {
        const match = text.match(/@[^\s]*$/);
        return match !== null;
    }

    getFileSearchText(text) {
        const match = text.match(/@([^\s]*)$/);
        return match ? match[1] : '';
    }

    showFileSuggestions(suggestions) {
        const inputArea = this.shadowRoot.querySelector('.chat-input-area');
        let suggestionsEl = inputArea.querySelector('.file-suggestions');
        
        if (!suggestionsEl) {
            suggestionsEl = document.createElement('div');
            suggestionsEl.className = 'file-suggestions';
            inputArea.insertBefore(suggestionsEl, this.input);
        }

        if (suggestions.length > 0) {
            suggestionsEl.innerHTML = suggestions.map(suggestion => `
                <div class="file-suggestion" data-path="${suggestion.path}">
                    <span class="icon">${suggestion.icon}</span>
                    <span class="name">${suggestion.name}</span>
                    <span class="path">${suggestion.path}</span>
                </div>
            `).join('');
            suggestionsEl.classList.add('show');

            suggestionsEl.querySelectorAll('.file-suggestion').forEach(el => {
                el.addEventListener('click', () => {
                    this.completeFileReference(el.dataset.path);
                });
            });
        } else {
            this.hideFileSuggestions();
        }
    }

    hideFileSuggestions() {
        const suggestions = this.shadowRoot.querySelector('.file-suggestions');
        if (suggestions) {
            suggestions.classList.remove('show');
        }
    }

    completeFileReference(path) {
        const cursorPosition = this.input.selectionStart;
        const textBeforeCursor = this.input.value.substring(0, cursorPosition);
        const textAfterCursor = this.input.value.substring(cursorPosition);
        
        // Replace the @text with the file reference
        const newTextBeforeCursor = textBeforeCursor.replace(/@[^\s]*$/, `@${path}`);
        
        this.input.value = newTextBeforeCursor + textAfterCursor;
        this.input.focus();
        // Place cursor after the inserted reference
        const newCursorPosition = newTextBeforeCursor.length;
        this.input.setSelectionRange(newCursorPosition, newCursorPosition);
        
        this.hideFileSuggestions();
    }

    clearMessages() {
        if (this.messagesContainer) {
            this.messagesContainer.innerHTML = '';
        }
    }

    async processUserMessage(content) {
        try {
            // Emit event for app-level handling
            this.dispatchEvent(new CustomEvent('processMessage', {
                bubbles: true,
                detail: { content }
            }));
        } catch (error) {
            this.addMessage('assistant', `Error: ${error.message}`);
        }
    }

    // Method to be called from app level to update output
    updateOutput(data) {
        switch (data.type) {
            case 'stdout':
                this.addMessage('assistant', data.data);
                break;
            case 'stderr':
                this.addSystemMessage(data.data, 'error');
                break;
            case 'status':
                this.addSystemMessage(data.data, 'status');
                break;
        }
    }
}

customElements.define('chat-box', ChatBox); 