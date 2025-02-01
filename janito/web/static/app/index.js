// Main application entry point
import { setupFileExplorer } from './file-explorer.js';
import { setupCodeEditor } from './code-editor.js';
import { setupChatBox } from './chat-box.js';

document.addEventListener('DOMContentLoaded', function() {
    const chatBoxContainer = document.getElementById('chatBoxContainer');
    const codeEditor = document.getElementById('codeEditor');
    const fileExplorer = document.getElementById('mainExplorer');
    
    // Initialize Socket.IO
    const socket = io('http://localhost:8000', {
        transports: ['websocket'],
        upgrade: false
    });
    
    // Ensure the ResizableSeparator component is loaded
    import('../components/resizable-separator.js');
    
    // Load initial saved widths from localStorage
    const savedExplorerWidth = localStorage.getItem('mainExplorer-width');
    const savedChatWidth = localStorage.getItem('chatBoxContainer-width');
    
    console.log('Initial saved widths:', { savedExplorerWidth, savedChatWidth });
    
    if (savedExplorerWidth) {
        fileExplorer.style.width = `${savedExplorerWidth}px`;
        console.log('Set explorer width:', savedExplorerWidth);
    }
    if (savedChatWidth && !chatBoxContainer.classList.contains('minimized')) {
        chatBoxContainer.style.width = `${savedChatWidth}px`;
        console.log('Set chat width:', savedChatWidth);
    }
    
    setupExplorerComponent(fileExplorer, chatBoxContainer);
    setupEditorComponent(codeEditor);
    setupChatBox(chatBoxContainer);
    
    // Function to update separator state
    function updateSeparatorState(isMinimized) {
        const separator = chatBoxContainer.previousElementSibling;
        console.log('Updating separator state:', { 
            isMinimized, 
            separatorFound: !!separator,
            separatorType: separator?.tagName
        });
        
        if (separator && separator.tagName.toLowerCase() === 'resizable-separator') {
            separator.updateLayout(isMinimized);
            if (!isMinimized) {
                console.log('Re-enabling separator resize functionality');
                separator.style.pointerEvents = 'auto';
                separator.style.cursor = 'ew-resize';
            }
        }
    }
    
    // Handle chat box state changes
    chatBoxContainer.addEventListener('chatStateChange', (event) => {
        const { isMinimized } = event.detail;
        console.log('Chat state change:', { 
            isMinimized, 
            currentWidth: chatBoxContainer.offsetWidth,
            savedWidth: localStorage.getItem('chatBoxContainer-width')
        });
        
        if (isMinimized) {
            // Just set to minimized width, don't save it
            chatBoxContainer.style.width = '40px';
        } else {
            // Restore previous width
            const savedWidth = localStorage.getItem('chatBoxContainer-width') || '300';
            console.log('Restoring width:', savedWidth);
            chatBoxContainer.style.width = `${savedWidth}px`;
        }
        
        updateSeparatorState(isMinimized);
    });
    
    // Listen for separator resize events - this is where we actually save the width
    document.addEventListener('separatorResize', (event) => {
        const { element, width, position } = event.detail;
        console.log('Separator resize:', { 
            elementId: element.id, 
            width, 
            position,
            currentWidth: element.offsetWidth
        });
        
        // Only save width if the element isn't minimized
        if (element.id && !element.classList.contains('minimized')) {
            localStorage.setItem(`${element.id}-width`, width);
            console.log(`Saved width for ${element.id}:`, width);
        }
    });

    // Process management functions
    async function startProcess(command, args = []) {
        try {
            const response = await fetch('http://localhost:8000/api/processes', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ command, args })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start process');
            }

            const { process_id } = await response.json();
            console.log('Process started with ID:', process_id);
            return process_id;
        } catch (error) {
            console.error('Error starting process:', error);
            throw error;
        }
    }

    async function stopProcess(processId) {
        if (!processId) return;
        try {
            await fetch(`http://localhost:8000/api/processes/${processId}`, {
                method: 'DELETE'
            });
            console.log('Process terminated:', processId);
        } catch (error) {
            console.error('Error stopping process:', error);
        }
    }

    // Handle chat messages
    chatBoxContainer.addEventListener('chat-message', async (event) => {
        console.log('Received chat message event:', event.detail);
        const chatBox = chatBoxContainer.querySelector('chat-box');
        if (!chatBox) return;

        try {
            const processId = await startProcess('janito', [event.detail.content]);
            console.log('Started process with ID:', processId);
            
            // Set up socket listener for this process
            socket.on(`process_output_${processId}`, (data) => {
                console.log(`Received process output for ${processId}:`, data);
                switch (data.type) {
                    case 'stdout':
                        chatBox.addMessage('assistant', data.data);
                        break;
                    case 'stderr':
                        chatBox.addMessage('assistant', `Error: ${data.data}`);
                        break;
                    case 'status':
                        chatBox.addMessage('assistant', `Status: ${data.data}`);
                        break;
                }
            });

        } catch (error) {
            console.error('Process start error:', error);
            chatBox.addMessage('assistant', `Error: ${error.message}`);
        }
    });

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        // Clean up any active processes if needed
    });

    setupDragAndDrop();
}); 

function setupEditorComponent(codeEditor) {
    // Add file-selected event listener
    document.addEventListener('file-selected', (event) => {
        console.log('File selected event received:', event.detail);
        if (codeEditor) {
            // Get the editor container and its next separator
            const editorContainer = codeEditor.closest('.editor-container');
            const nextSeparator = editorContainer.nextElementSibling;
            
            // If editor was closed, restore it
            if (editorContainer.style.display === 'none') {
                // Show editor and its separator
                editorContainer.style.display = 'flex';
                if (nextSeparator && nextSeparator.tagName.toLowerCase() === 'resizable-separator') {
                    nextSeparator.style.display = 'block';
                }
                
                // Reset chat box to its default state
                const chatBoxContainer = document.getElementById('chatBoxContainer');
                if (chatBoxContainer) {
                    chatBoxContainer.classList.remove('expanded');
                    chatBoxContainer.style.flex = '';
                    const savedChatWidth = localStorage.getItem('chatBoxContainer-width') || '300';
                    chatBoxContainer.style.width = `${savedChatWidth}px`;
                }
                
                // Update editor state
                localStorage.setItem('editor-state', 'open');
            }
            
            codeEditor.setAttribute('file-extension', event.detail.fileExtension);
            codeEditor.setContent(event.detail.content);
        }
    });

    // Add minimize/close handlers
    codeEditor.addEventListener('minimize', (event) => {
        // Store current width before minimizing
        const currentWidth = codeEditor.offsetWidth;
        localStorage.setItem('codeEditor-prev-width', currentWidth);
        
        // Minimize the editor
        codeEditor.classList.add('minimized');
        codeEditor.style.width = '40px';
        
        // Update separator state
        const separator = codeEditor.nextElementSibling;
        if (separator && separator.tagName.toLowerCase() === 'resizable-separator') {
            separator.updateLayout(true);
        }
    });

    codeEditor.addEventListener('close', (event) => {
        // Get the editor container and its next separator
        const editorContainer = codeEditor.closest('.editor-container');
        const nextSeparator = editorContainer.nextElementSibling;
        const prevSeparator = editorContainer.previousElementSibling;
        
        // Store the current layout state
        localStorage.setItem('editor-state', 'closed');
        
        // Hide the editor container and its next separator
        editorContainer.style.display = 'none';
        if (nextSeparator && nextSeparator.tagName.toLowerCase() === 'resizable-separator') {
            nextSeparator.style.display = 'none';
        }
        
        // Get the chat box container
        const chatBoxContainer = document.getElementById('chatBoxContainer');
        if (chatBoxContainer && !chatBoxContainer.classList.contains('minimized')) {
            // Remove any explicit width to allow flex layout to take over
            chatBoxContainer.style.width = '';
            chatBoxContainer.style.flex = '1';
            chatBoxContainer.classList.add('expanded');
            
            // Update the first separator to control explorer vs chat box
            if (prevSeparator && prevSeparator.tagName.toLowerCase() === 'resizable-separator') {
                prevSeparator.removeEventListener('mousedown', prevSeparator.startResize);
                prevSeparator.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    const explorer = document.querySelector('.sidebar');
                    const startX = e.pageX;
                    const explorerStartWidth = explorer.offsetWidth;
                    
                    function handleResize(e) {
                        const delta = e.pageX - startX;
                        const newWidth = Math.max(200, Math.min(explorerStartWidth + delta, window.innerWidth - 200));
                        explorer.style.width = `${newWidth}px`;
                        localStorage.setItem('mainExplorer-width', newWidth);
                    }
                    
                    function stopResize() {
                        window.removeEventListener('mousemove', handleResize);
                        window.removeEventListener('mouseup', stopResize);
                    }
                    
                    window.addEventListener('mousemove', handleResize);
                    window.addEventListener('mouseup', stopResize);
                });
            }
        }
    });
} 

function setupExplorerComponent(fileExplorer, chatBoxContainer) {
    const explorerMenuConfig = [
        {
            label: 'Add to Chat Box',
            icon: '📄',
            action: (path, isDirectory) => {
                console.log('Add to Chat Box action triggered:', { path, isDirectory });
                chatBoxContainer.classList.add('show');
                const chatBox = document.querySelector('chat-box');
                console.log('Found chat box:', chatBox);
                if (chatBox) {
                    console.log('Calling addFileToggle with:', { path, isDirectory });
                    chatBox.addFileToggle(path, isDirectory ? 'directory' : 'file', false);
                } else {
                    console.error('Chat box element not found');
                }
            },
            showFor: 'both'
        },
        {
            label: 'Add to Chat Box (Recursive)',
            icon: '🔄',
            action: (path) => {
                console.log('Add to Chat Box (Recursive) action triggered:', path);
                chatBoxContainer.classList.add('show');
                const chatBox = document.querySelector('chat-box');
                console.log('Found chat box:', chatBox);
                if (chatBox) {
                    console.log('Calling addFileToggle with recursive:', path);
                    chatBox.addFileToggle(path, 'directory', true);
                } else {
                    console.error('Chat box element not found');
                }
            },
            showFor: 'directory'  // Only show for directories
        }
    ];

    fileExplorer.setContextMenu(explorerMenuConfig);

    // Add minimize/close handlers
    fileExplorer.addEventListener('minimize', (event) => {
        // Store current width before minimizing
        const currentWidth = fileExplorer.parentElement.offsetWidth;
        localStorage.setItem('mainExplorer-prev-width', currentWidth);
        
        // Minimize the explorer
        fileExplorer.parentElement.classList.add('minimized');
        fileExplorer.parentElement.style.width = '40px';
        
        // Update separator state
        const separator = fileExplorer.parentElement.nextElementSibling;
        if (separator && separator.tagName.toLowerCase() === 'resizable-separator') {
            separator.updateLayout(true);
        }
    });

    fileExplorer.addEventListener('close', (event) => {
        fileExplorer.parentElement.style.display = 'none';
    });
} 

function setupDragAndDrop() {
    let dragData = null;

    // Listen for drag start from file explorer
    document.addEventListener('explorer-dragstart', (event) => {
        dragData = event.detail;
        
        // Update cursor based on recursive state
        if (dragData.type === 'directory') {
            const style = document.createElement('style');
            style.id = 'drag-cursor-style';
            style.textContent = `
                .file-toggles.drag-over::after {
                    content: '${dragData.recursive ? 'Drop to add (Recursive)' : 'Drop to add'}';
                }
            `;
            document.head.appendChild(style);
        }
    });

    // Listen for drop on chat box
    document.addEventListener('chatbox-drop', async (event) => {
        if (dragData && event.detail.path === dragData.path) {
            const chatBox = document.querySelector('chat-box');
            if (chatBox) {
                await chatBox.addFileToggle(
                    dragData.path, 
                    dragData.type,
                    dragData.recursive
                );
            }
        }
        dragData = null;
        
        // Clean up cursor style
        const cursorStyle = document.getElementById('drag-cursor-style');
        if (cursorStyle) {
            cursorStyle.remove();
        }
    });

    // Clean up on drag end
    document.addEventListener('dragend', () => {
        const cursorStyle = document.getElementById('drag-cursor-style');
        if (cursorStyle) {
            cursorStyle.remove();
        }
        dragData = null;
    });
} 