class CodeOutput extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.setupOutput();
    }

    setupOutput() {
        const style = document.createElement('style');
        style.textContent = `
            :host {
                display: block;
                width: 100%;
                min-height: 150px;
                background-color: var(--editor-bg);
                border-radius: 4px;
                overflow: hidden;
                border: 1px solid #444;
                margin-top: 20px;
            }

            .output-header {
                background-color: #252526;
                padding: 8px 10px;
                border-bottom: 1px solid #444;
                font-size: 12px;
                color: #ccc;
            }

            .output {
                padding: 10px;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                line-height: 1.5;
                color: var(--editor-text);
                white-space: pre-wrap;
                word-wrap: break-word;
                min-height: 100px;
                max-height: 300px;
                overflow-y: auto;
            }

            .error {
                color: #f44336;
            }

            .output:empty::before {
                content: '// Output will appear here';
                color: #666;
                font-style: italic;
            }
        `;

        const outputHeader = document.createElement('div');
        outputHeader.className = 'output-header';
        outputHeader.textContent = 'Output';

        const output = document.createElement('div');
        output.className = 'output';

        this.shadowRoot.appendChild(style);
        this.shadowRoot.appendChild(outputHeader);
        this.shadowRoot.appendChild(output);

        this.outputElement = output;
    }

    setOutput(text, isError = false) {
        this.outputElement.textContent = text;
        this.outputElement.className = isError ? 'output error' : 'output';
    }
}

customElements.define('code-output', CodeOutput);