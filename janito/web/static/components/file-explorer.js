class FileExplorer extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.currentPath = '.';
        this.lastClickTime = 0;
        this.lastClickPath = null;
        this.contextMenuConfig = [];
        this.setupExplorer();
    }

    setContextMenu(config) {
        console.log('Setting context menu with config:', config);
        this.contextMenuConfig = config.map(item => ({
            ...item,
            action: (...args) => {
                console.log(`Menu item "${item.label}" clicked with args:`, args);
                return item.action(...args);
            }
        }));
    }

    setupExplorer() {
        const style = document.createElement('style');
        style.textContent = `
            :host {
                display: block;
                background-color: #252526;
                color: #d4d4d4;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 13px;
                height: 100%;
                overflow: auto;
            }

            .explorer-container {
                display: flex;
                flex-direction: column;
                height: 100%;
            }

            .explorer-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 3px 8px;
                height: 24px;
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
                user-select: none;
            }

            .explorer-header-title {
                font-size: 11px;
                text-transform: uppercase;
                font-weight: bold;
                color: #bbbbbb;
                line-height: 18px;
            }

            .explorer-header-actions {
                display: flex;
                gap: 8px;
            }

            .explorer-header-button {
                padding: 2px 4px;
                cursor: pointer;
                opacity: 0.8;
                background: none;
                border: none;
                color: #bbbbbb;
                font-size: 14px;
                line-height: 18px;
            }

            .explorer-header-button:hover {
                opacity: 1;
            }

            .folder-list {
                list-style: none;
                padding: 0;
                margin: 0;
                flex: 1;
                overflow: auto;
            }

            .folder-item {
                display: flex;
                align-items: center;
                padding: 3px 12px;
                cursor: pointer;
                user-select: none;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                position: relative;
                transition: background-color 0.1s;
            }

            .folder-item:hover {
                background-color: #2a2d2e;
            }

            .folder-item.selected {
                background-color: #37373d;
            }

            .folder-item.loading {
                opacity: 0.7;
                pointer-events: none;
            }

            .folder-item.directory {
                position: relative;
            }

            .folder-item.directory::before {
                content: '▶';
                font-size: 8px;
                margin-right: 6px;
                color: #bbbbbb;
                transition: transform 0.1s;
            }

            .folder-item.directory.expanded::before {
                transform: rotate(90deg);
            }

            .folder-item.file {
                padding-left: 24px;
            }

            .folder-item.python-file,
            .folder-item.js-file,
            .folder-item.css-file,
            .folder-item.html-file {
                position: relative;
            }

            .folder-item.python-file::before {
                content: '🐍';
                font-size: 12px;
                margin-right: 6px;
                opacity: 0.8;
                transition: opacity 0.1s;
            }

            .folder-item.js-file::before {
                content: '📜';
                font-size: 12px;
                margin-right: 6px;
                opacity: 0.8;
                transition: opacity 0.1s;
            }

            .folder-item.css-file::before {
                content: '🎨';
                font-size: 12px;
                margin-right: 6px;
                opacity: 0.8;
                transition: opacity 0.1s;
            }

            .folder-item.html-file::before {
                content: '🌐';
                font-size: 12px;
                margin-right: 6px;
                opacity: 0.8;
                transition: opacity 0.1s;
            }

            .folder-item.python-file:hover::before,
            .folder-item.js-file:hover::before,
            .folder-item.css-file:hover::before,
            .folder-item.html-file:hover::before {
                opacity: 1;
            }

            .nested {
                padding-left: 12px;
                display: none;
                animation: slideDown 0.2s ease-out;
            }

            .nested.show {
                display: block;
            }

            @keyframes slideDown {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .breadcrumb {
                padding: 4px 12px;
                font-size: 12px;
                color: #bbbbbb;
                border-bottom: 1px solid #3c3c3c;
                display: flex;
                align-items: center;
                gap: 4px;
            }

            .breadcrumb-item {
                cursor: pointer;
                transition: color 0.1s;
            }

            .breadcrumb-item:hover {
                color: #ffffff;
            }

            .breadcrumb-separator {
                color: #666;
            }

            .error-message {
                color: #f44336;
                padding: 8px 12px;
                font-size: 12px;
                animation: fadeIn 0.3s ease-out;
            }

            @keyframes fadeIn {
                from {
                    opacity: 0;
                }
                to {
                    opacity: 1;
                }
            }

            .loading-indicator {
                position: absolute;
                right: 8px;
                width: 12px;
                height: 12px;
                border: 2px solid #bbbbbb;
                border-radius: 50%;
                border-top-color: transparent;
                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                to {
                    transform: rotate(360deg);
                }
            }
        `;

        const container = document.createElement('div');
        container.className = 'explorer-container';

        const header = document.createElement('div');
        header.className = 'explorer-header';
        header.innerHTML = `
            <div class="explorer-header-title">Explorer</div>
            <div class="explorer-header-actions">
                <button class="explorer-header-button minimize-button">−</button>
                <button class="explorer-header-button close-button">×</button>
            </div>
        `;

        const breadcrumb = document.createElement('div');
        breadcrumb.className = 'breadcrumb';

        const folderList = document.createElement('ul');
        folderList.className = 'folder-list';

        container.appendChild(header);
        container.appendChild(breadcrumb);
        container.appendChild(folderList);

        this.shadowRoot.appendChild(style);
        this.shadowRoot.appendChild(container);

        this.folderList = folderList;
        this.breadcrumb = breadcrumb;

        // Add header button handlers
        const minimizeButton = header.querySelector('.minimize-button');
        const closeButton = header.querySelector('.close-button');

        minimizeButton.addEventListener('click', () => {
            this.dispatchEvent(new CustomEvent('minimize', {
                bubbles: true,
                composed: true
            }));
        });

        closeButton.addEventListener('click', () => {
            this.dispatchEvent(new CustomEvent('close', {
                bubbles: true,
                composed: true
            }));
        });

        this.setupEventListeners();
        this.loadDirectory(this.currentPath);
    }

    setupEventListeners() {
        this.folderList.addEventListener('click', (e) => {
            const item = e.target.closest('.folder-item');
            if (!item || item.classList.contains('loading')) return;

            const path = item.dataset.path;
            console.log('Click detected on item:', item);

            if (item.classList.contains('directory')) {
                console.log('Directory clicked:', path);
                const parentList = item.closest('.folder-list');
                let nested = parentList.querySelector(`[data-path="${path}"] + .nested`);
                
                if (nested) {
                    // Toggle existing nested list
                    console.log('Toggling existing nested list');
                    item.classList.toggle('expanded');
                    nested.classList.toggle('show');
                } else {
                    // Create and load new nested list
                    console.log('Creating new nested list');
                    nested = document.createElement('ul');
                    nested.className = 'folder-list nested';
                    item.after(nested);
                    item.classList.add('expanded');
                    nested.classList.add('show');
                    
                    // Load the directory contents
                    this.loadDirectory(path, nested);
                }
            } else if (item.classList.contains('file')) {
                console.log('File clicked:', path);
                
                // Load file on single click
                if (!item.classList.contains('loading')) {
                    console.log('Starting file load process');
                    item.classList.add('loading');
                    this.loadFile(path)
                        .then(() => {
                            console.log('File load completed successfully for:', path);
                            item.classList.remove('loading');
                        })
                        .catch(error => {
                            console.error('Error in file load process:', error);
                            item.classList.remove('loading');
                            this.showError('Failed to load file');
                        });
                }
                
                // Select the item
                this.selectItem(item);
            }
        });

        // Add context menu event listener to folder items
        this.folderList.addEventListener('contextmenu', (e) => {
            const item = e.target.closest('.folder-item');
            if (!item) return;

            const path = item.dataset.path;
            const isDirectory = item.classList.contains('directory');
            console.log('Context menu triggered for:', path, 'isDirectory:', isDirectory);
            this.showContextMenu(e, path, isDirectory);
        });

        this.breadcrumb.addEventListener('click', (e) => {
            const item = e.target.closest('.breadcrumb-item');
            if (item) {
                const path = item.dataset.path;
                this.loadDirectory(path);
            }
        });

        // Add drag event listeners to folder items
        this.folderList.addEventListener('dragstart', (e) => {
            const item = e.target.closest('.folder-item');
            if (!item) return;

            const path = item.dataset.path;
            const isDirectory = item.classList.contains('directory');
            const isCtrlPressed = e.ctrlKey;
            
            // Dispatch custom event with drag data
            const dragEvent = new CustomEvent('explorer-dragstart', {
                bubbles: true,
                composed: true,
                detail: { 
                    path, 
                    type: isDirectory ? 'directory' : 'file',
                    recursive: isDirectory && isCtrlPressed
                }
            });
            this.dispatchEvent(dragEvent);
            
            // Set drag data for native drag and drop
            e.dataTransfer.setData('text/plain', path);
            e.dataTransfer.effectAllowed = 'copy';

            // Update cursor to indicate recursive mode
            if (isDirectory && isCtrlPressed) {
                e.dataTransfer.setDragImage(item, 0, 0);  // Keep original drag image
                item.style.cursor = 'copy';
                // Store the item for cleanup
                this._draggedItem = item;
            }
        });

        // Add dragend listener to clean up cursor style
        this.folderList.addEventListener('dragend', (e) => {
            if (this._draggedItem) {
                this._draggedItem.style.cursor = '';
                this._draggedItem = null;
            }
        });

        // Make items draggable
        const makeDraggable = (item) => {
            item.draggable = true;
        };

        // Apply draggable to existing items
        this.folderList.querySelectorAll('.folder-item').forEach(makeDraggable);
    }

    async loadDirectory(path, targetElement) {
        try {
            console.log('Loading directory:', path);
            const response = await fetch(`http://localhost:8000/api/files?path=${encodeURIComponent(path)}`);
            if (!response.ok) throw new Error('Failed to load directory');
            
            const files = await response.json();
            this.currentPath = path;
            this.updateBreadcrumb();

            // Clear the target element if it's a nested list
            if (targetElement && targetElement.classList.contains('nested')) {
                targetElement.innerHTML = '';
            } else {
                // If no target specified or not nested, use the main folder list
                targetElement = this.folderList;
                targetElement.innerHTML = '';
            }

            files.forEach(file => {
                const item = document.createElement('li');
                item.className = `folder-item ${file.type}`;
                
                // Add file type specific classes
                if (file.type === 'file') {
                    const extension = file.name.split('.').pop().toLowerCase();
                    switch (extension) {
                        case 'py':
                            item.classList.add('python-file');
                            break;
                        case 'js':
                            item.classList.add('js-file');
                            break;
                        case 'css':
                            item.classList.add('css-file');
                            break;
                        case 'html':
                        case 'htm':
                            item.classList.add('html-file');
                            break;
                    }
                }

                item.textContent = file.name;
                item.dataset.path = file.path;
                item.draggable = true;  // Make item draggable
                targetElement.appendChild(item);
            });
        } catch (error) {
            console.error('Error loading directory:', error);
            this.showError('Failed to load directory');
        }
    }

    async loadFile(path) {
        console.log('loadFile called with path:', path);
        try {
            console.log('Fetching file content from API');
            const response = await fetch(`http://localhost:8000/api/files/content?path=${encodeURIComponent(path)}`);
            
            if (!response.ok) {
                console.error('API response not OK:', response.status, response.statusText);
                throw new Error('Failed to load file');
            }
            
            const data = await response.json();
            console.log('File content received:', data);
            
            // Get file extension from path
            const fileExtension = path.split('.').pop().toLowerCase();
            
            // Dispatch custom event with file extension
            const event = new CustomEvent('file-selected', {
                bubbles: true,
                composed: true,
                detail: {
                    filePath: path,
                    content: data.content,
                    fileExtension: fileExtension
                }
            });
            this.dispatchEvent(event);
            console.log('File selected event dispatched with extension:', fileExtension);
            
        } catch (error) {
            console.error('Error in loadFile:', error);
            this.showError('Failed to load file');
            throw error;
        }
    }

    updateBreadcrumb() {
        this.breadcrumb.innerHTML = '';
        const parts = this.currentPath.split('/').filter(Boolean);
        
        const root = document.createElement('span');
        root.className = 'breadcrumb-item';
        root.textContent = 'root';
        root.dataset.path = '.';
        this.breadcrumb.appendChild(root);

        parts.forEach((part, index) => {
            const separator = document.createElement('span');
            separator.className = 'breadcrumb-separator';
            separator.textContent = '/';
            this.breadcrumb.appendChild(separator);

            const item = document.createElement('span');
            item.className = 'breadcrumb-item';
            item.textContent = part;
            item.dataset.path = parts.slice(0, index + 1).join('/');
            this.breadcrumb.appendChild(item);
        });
    }

    selectItem(item) {
        const selected = this.shadowRoot.querySelector('.folder-item.selected');
        if (selected) {
            selected.classList.remove('selected');
        }
        item.classList.add('selected');
    }

    showError(message) {
        const error = document.createElement('div');
        error.className = 'error-message';
        error.textContent = message;
        this.folderList.insertAdjacentElement('beforebegin', error);
        setTimeout(() => error.remove(), 3000);
    }

    showContextMenu(e, path, isDirectory) {
        console.log('Showing context menu for:', { path, isDirectory });
        e.preventDefault();
        e.stopPropagation();

        // Remove any existing context menu
        const existingMenu = document.querySelector('.context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        // Filter menu items based on type
        const menuItems = this.contextMenuConfig.filter(menuItem => {
            if (menuItem.showFor === 'both') return true;
            if (menuItem.showFor === 'file' && !isDirectory) return true;
            if (menuItem.showFor === 'directory' && isDirectory) return true;
            return false;
        });

        console.log('Filtered menu items:', menuItems);

        // Create and show context menu
        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.style.position = 'fixed';
        menu.style.left = `${e.clientX}px`;
        menu.style.top = `${e.clientY}px`;
        menu.style.zIndex = '1000';
        menu.style.backgroundColor = '#252526';
        menu.style.border = '1px solid #3c3c3c';
        menu.style.padding = '4px 0';
        menu.style.borderRadius = '3px';
        menu.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.15)';

        menu.innerHTML = menuItems.map(item => `
            <div class="context-menu-item" data-label="${item.label}" style="
                padding: 4px 12px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                color: #d4d4d4;
                font-size: 13px;
                white-space: nowrap;
            ">
                <span class="icon">${item.icon}</span>
                ${item.label}
            </div>
        `).join('');

        // Handle menu item clicks
        menu.addEventListener('click', (menuEvent) => {
            const menuItem = menuEvent.target.closest('.context-menu-item');
            if (menuItem) {
                const label = menuItem.dataset.label;
                const action = this.contextMenuConfig.find(item => item.label === label);
                if (action) {
                    console.log('Executing menu action:', label);
                    action.action(path, isDirectory);
                }
            }
            menu.remove();
        });

        // Remove menu when clicking outside
        const removeMenu = (e) => {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', removeMenu);
            }
        };
        document.addEventListener('click', removeMenu);

        // Append to document body
        document.body.appendChild(menu);
    }
}

customElements.define('file-explorer', FileExplorer);