class CodeEditor extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.tokenizer = new SyntaxTokenizer();
        this.currentLanguage = 'python';  // Default language
        this.setupEditor();
    }

    setupEditor() {
        const style = document.createElement('style');
        style.textContent = `
            :host {
                display: block;
                position: relative;
                height: 100%;
            }

            .editor-container {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: var(--editor-bg);
                display: flex;
                flex-direction: column;
            }

            /* Add header styles similar to chat box */
            .editor-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 4px 8px;
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
                user-select: none;
            }

            .editor-header-title {
                font-size: 11px;
                text-transform: uppercase;
                font-weight: bold;
                color: #bbbbbb;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .language-mode {
                color: #666;
                font-weight: normal;
            }

            .editor-header-actions {
                display: flex;
                gap: 8px;
            }

            .editor-header-button {
                padding: 2px 4px;
                cursor: pointer;
                opacity: 0.8;
                background: none;
                border: none;
                color: #bbbbbb;
                font-size: 14px;
            }

            .editor-header-button:hover {
                opacity: 1;
            }

            /* Update editor content styles */
            .editor-content {
                position: relative;
                flex: 1;
                overflow: hidden;
            }

            .editor-wrapper {
                position: relative;
                height: 100%;
                padding: 10px 10px 10px 0;  /* Remove left padding */
                box-sizing: border-box;
                overflow-y: auto;
                display: flex;  /* Add flex display */
            }

            .line-numbers {
                padding: 0 8px;
                background-color: var(--editor-bg);
                color: #858585;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                line-height: 1.5;
                text-align: right;
                user-select: none;
                min-width: 40px;
                border-right: 1px solid #3c3c3c;
            }

            .editor-main {
                flex: 1;
                position: relative;
                padding-left: 10px;
            }

            .editor {
                position: absolute;
                top: 0;
                left: 10px;  /* Match padding of editor-main */
                right: 0;
                height: auto;
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                line-height: 1.5;
                color: transparent;
                caret-color: var(--editor-text);
                background: transparent;
                border: none;
                resize: none;
                outline: none;
                white-space: pre-wrap;
                word-wrap: break-word;
                word-break: break-all;
                tab-size: 4;
                z-index: 2;
                overflow: hidden;
            }

            .highlight {
                position: absolute;
                top: 0;
                left: 10px;  /* Match padding of editor-main */
                right: 0;
                height: auto;
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                line-height: 1.5;
                color: var(--editor-text);
                background: transparent;
                white-space: pre-wrap;
                word-wrap: break-word;
                word-break: break-all;
                pointer-events: none;
                tab-size: 4;
                z-index: 1;
                overflow: hidden;
            }

            .token-keyword { color: var(--keyword-color); }
            .token-string { color: var(--string-color); }
            .token-comment { color: var(--comment-color); }
            .token-number { color: var(--number-color); }
            .token-operator { color: #c586c0; }
            .token-delimiter { color: #d4d4d4; }
            .token-identifier { color: #9cdcfe; }
            .token-whitespace { color: inherit; }
            .token-unknown { color: #d4d4d4; }
            .token-tag { color: #569cd6; }
            .token-attribute { color: #9cdcfe; }
            .token-selector { color: #d7ba7d; }
            .token-property { color: #9cdcfe; }
            .token-value { color: #ce9178; }
        `;

        const container = document.createElement('div');
        container.className = 'editor-container';

        // Add header section
        const header = document.createElement('div');
        header.className = 'editor-header';
        header.innerHTML = `
            <div class="editor-header-title">
                Editor <span class="language-mode">(Python)</span>
            </div>
            <div class="editor-header-actions">
                <button class="editor-header-button minimize-button">−</button>
                <button class="editor-header-button close-button">×</button>
            </div>
        `;

        const content = document.createElement('div');
        content.className = 'editor-content';

        const wrapper = document.createElement('div');
        wrapper.className = 'editor-wrapper';

        const lineNumbers = document.createElement('div');
        lineNumbers.className = 'line-numbers';

        const editorMain = document.createElement('div');
        editorMain.className = 'editor-main';

        const textarea = document.createElement('textarea');
        textarea.className = 'editor';
        textarea.spellcheck = false;
        textarea.value = this.textContent.trim();

        const highlight = document.createElement('div');
        highlight.className = 'highlight';

        editorMain.appendChild(highlight);
        editorMain.appendChild(textarea);
        wrapper.appendChild(lineNumbers);
        wrapper.appendChild(editorMain);
        content.appendChild(wrapper);

        container.appendChild(header);
        container.appendChild(content);
        content.appendChild(wrapper);

        this.shadowRoot.appendChild(style);
        this.shadowRoot.appendChild(container);

        this.container = container;
        this.content = content;
        this.wrapper = wrapper;
        this.textarea = textarea;
        this.highlight = highlight;
        this.languageMode = header.querySelector('.language-mode');
        this.lineNumbers = lineNumbers;

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
        this.updateHighlight();
        this.updateSize();
        this.updateLineNumbers();
    }

    setupEventListeners() {
        this.textarea.addEventListener('input', () => {
            this.updateHighlight();
            this.updateSize();
            this.updateLineNumbers();
        });

        this.textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = this.textarea.selectionStart;
                const end = this.textarea.selectionEnd;
                this.textarea.value = this.textarea.value.substring(0, start) + '    ' + 
                                    this.textarea.value.substring(end);
                this.textarea.selectionStart = this.textarea.selectionEnd = start + 4;
                this.updateHighlight();
                this.updateSize();
            }
        });

        // Handle initial load and resize
        window.addEventListener('resize', () => this.updateSize());
        setTimeout(() => this.updateSize(), 0);
    }

    updateHighlight() {
        const code = this.textarea.value;
        const fileExtension = this.getAttribute('file-extension') || 'py';
        
        // Determine language based on file extension
        const languageMap = {
            'py': 'python',
            'js': 'javascript',
            'html': 'html',
            'css': 'css'
        };
        const newLanguage = languageMap[fileExtension] || 'python';
        
        // Only dispatch event if language changed
        if (this.currentLanguage !== newLanguage) {
            this.currentLanguage = newLanguage;
            // Dispatch language change event
            const event = new CustomEvent('language-changed', {
                bubbles: true,
                composed: true,
                detail: { language: this.currentLanguage }
            });
            this.dispatchEvent(event);
        }
        
        const tokens = this.tokenizer.tokenize(code, this.currentLanguage);
        
        let html = '';
        for (const token of tokens) {
            const escapedValue = token.value
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            html += `<span class="token-${token.type}">${escapedValue}</span>`;
        }

        this.highlight.innerHTML = html;
    }

    updateLineNumbers() {
        const lines = this.textarea.value.split('\n');
        this.lineNumbers.innerHTML = lines
            .map((_, index) => `<div>${index + 1}</div>`)
            .join('');
    }

    updateSize() {
        // Create a temporary div to measure the actual height
        const measureDiv = document.createElement('div');
        measureDiv.style.cssText = `
            position: absolute;
            visibility: hidden;
            height: auto;
            width: ${this.wrapper.clientWidth - 20}px; /* Account for padding */
            white-space: pre-wrap;
            word-wrap: break-word;
            word-break: break-all;
            font-family: 'Consolas', monospace;
            font-size: 14px;
            line-height: 1.5;
            padding: 10px;
        `;
        measureDiv.textContent = this.textarea.value + '\n';
        document.body.appendChild(measureDiv);
        
        // Get the actual height including wrapped lines
        const contentHeight = Math.max(measureDiv.scrollHeight, this.container.clientHeight);
        document.body.removeChild(measureDiv);
        
        // Set heights using the measured height
        this.textarea.style.minHeight = `${contentHeight}px`;
        this.highlight.style.minHeight = `${contentHeight}px`;

        // Update line numbers
        this.updateLineNumbers();
    }

    setContent(content) {
        this.textarea.value = content;
        this.updateHighlight();
        this.updateSize();
    }

    getContent() {
        return this.textarea.value;
    }

    // Update the language mode display when file extension changes
    attributeChangedCallback(name, oldValue, newValue) {
        super.attributeChangedCallback(name, oldValue, newValue);
        if (name === 'file-extension') {
            const extensionToLanguage = {
                'py': 'Python',
                'js': 'JavaScript',
                'html': 'HTML',
                'css': 'CSS'
            };
            const language = extensionToLanguage[newValue] || newValue.toUpperCase();
            if (this.languageMode) {
                this.languageMode.textContent = `(${language})`;
            }
        }
    }
}

customElements.define('code-editor', CodeEditor);