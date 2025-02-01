class ResizableSeparator extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.isDragging = false;
        
        // Bind the methods to ensure proper 'this' context
        this.startResize = this.startResize.bind(this);
        this.resize = this.resize.bind(this);
        this.stopResize = this.stopResize.bind(this);
        
        this.setupSeparator();
    }

    setupSeparator() {
        const style = document.createElement('style');
        style.textContent = `
            :host {
                width: 4px;
                background-color: #3c3c3c;
                cursor: ew-resize;
                flex-shrink: 0;
                transition: background-color 0.1s;
                touch-action: none;
                user-select: none;
                position: relative;
                z-index: 1000;
            }

            :host(:hover),
            :host(.dragging) {
                background-color: #0e639c;
            }
        `;

        this.shadowRoot.appendChild(style);

        // Remove any existing listeners before adding new ones
        this.removeEventListener('mousedown', this.startResize);
        document.removeEventListener('mousemove', this.resize);
        document.removeEventListener('mouseup', this.stopResize);
        
        // Add the event listeners
        this.addEventListener('mousedown', this.startResize);
        document.addEventListener('mousemove', this.resize);
        document.addEventListener('mouseup', this.stopResize);
    }

    startResize(e) {
        e.preventDefault();
        
        const nextElement = this.nextElementSibling;
        // Don't allow resizing if the chat box is minimized
        if (nextElement?.classList.contains('minimized')) {
            return;
        }

        this.isDragging = true;
        this.classList.add('dragging');
        this.startX = e.pageX;
        
        const prevElement = this.previousElementSibling;
        
        if (prevElement && nextElement) {
            this.prevWidth = prevElement.offsetWidth;
            this.nextWidth = nextElement.offsetWidth;
            this.totalWidth = this.prevWidth + this.nextWidth;
            
            this.prevMinWidth = prevElement.classList.contains('editor-container') ? 300 : 200;
            this.nextMinWidth = nextElement.classList.contains('chat-box-container') ? 200 : 200;

            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none';
        }
    }

    resize(e) {
        if (!this.isDragging) return;
        
        const nextElement = this.nextElementSibling;
        if (nextElement?.classList.contains('minimized')) {
            return;
        }

        requestAnimationFrame(() => {
            const prevElement = this.previousElementSibling;
            if (!prevElement || !nextElement) return;

            const delta = e.pageX - this.startX;
            
            let newPrevWidth = Math.max(this.prevMinWidth, Math.min(this.prevWidth + delta, this.totalWidth - this.nextMinWidth));
            let newNextWidth = this.totalWidth - newPrevWidth;
            
            if (newPrevWidth < this.prevMinWidth) {
                newPrevWidth = this.prevMinWidth;
                newNextWidth = this.totalWidth - this.prevMinWidth;
            } else if (newNextWidth < this.nextMinWidth) {
                newNextWidth = this.nextMinWidth;
                newPrevWidth = this.totalWidth - this.nextMinWidth;
            }
            
            prevElement.style.width = `${newPrevWidth}px`;
            nextElement.style.width = `${newNextWidth}px`;

            // Dispatch events for width changes with more detailed information
            document.dispatchEvent(new CustomEvent('separatorResize', {
                detail: { 
                    element: prevElement, 
                    width: newPrevWidth,
                    position: 'prev'
                }
            }));
            document.dispatchEvent(new CustomEvent('separatorResize', {
                detail: { 
                    element: nextElement, 
                    width: newNextWidth,
                    position: 'next'
                }
            }));
        });
    }

    stopResize() {
        if (!this.isDragging) return;
        this.isDragging = false;
        this.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }

    updateLayout(isMinimized) {
        if (isMinimized) {
            this.style.pointerEvents = 'none';
            this.style.cursor = 'default';
        } else {
            this.style.pointerEvents = 'auto';
            this.style.cursor = 'ew-resize';
        }
    }
}

// Ensure the component is only defined once
if (!customElements.get('resizable-separator')) {
    customElements.define('resizable-separator', ResizableSeparator);
} 