// File explorer configuration and setup
export function setupFileExplorer(fileExplorer, chatBoxContainer) {
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
            showFor: 'directory'
        },
        {
            label: 'Chat Box View',
            icon: '⌘',
            action: () => {
                chatBoxContainer.classList.add('show');
            },
            showFor: 'both'
        }
    ];

    fileExplorer.setContextMenu(explorerMenuConfig);
} 