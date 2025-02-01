class Token {
    constructor(type, value, start, end) {
        this.type = type;
        this.value = value;
        this.start = start;
        this.end = end;
    }
}

class SyntaxTokenizer {
    constructor() {
        this.pythonKeywords = new Set([
            'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
            'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
            'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
            'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return',
            'try', 'while', 'with', 'yield'
        ]);

        this.jsKeywords = new Set([
            'break', 'case', 'catch', 'class', 'const', 'continue', 'debugger',
            'default', 'delete', 'do', 'else', 'export', 'extends', 'finally',
            'for', 'function', 'if', 'import', 'in', 'instanceof', 'new', 'return',
            'super', 'switch', 'this', 'throw', 'try', 'typeof', 'var', 'void',
            'while', 'with', 'yield', 'let', 'static', 'enum', 'await', 'async',
            'true', 'false', 'null', 'undefined'
        ]);

        this.htmlTags = new Set([
            'html', 'head', 'body', 'div', 'span', 'p', 'a', 'img', 'script',
            'style', 'link', 'meta', 'title', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'form', 'input', 'button',
            'select', 'option', 'textarea', 'label', 'header', 'footer', 'nav',
            'main', 'section', 'article', 'aside', 'canvas', 'video', 'audio'
        ]);

        this.cssProperties = new Set([
            'color', 'background', 'margin', 'padding', 'border', 'font-size',
            'font-family', 'display', 'position', 'width', 'height', 'top',
            'right', 'bottom', 'left', 'flex', 'grid', 'transition', 'transform',
            'animation', 'box-shadow', 'text-align', 'line-height', 'opacity'
        ]);

        this.operators = new Set([
            '+', '-', '*', '/', '//', '%', '**', '=', '==', '!=', '<', '>',
            '<=', '>=', '+=', '-=', '*=', '/=', '//=', '%=', '**=', '&=',
            '|=', '^=', '>>=', '<<=', '&', '|', '^', '~', '<<', '>>', '=>'
        ]);

        this.delimiters = new Set(['(', ')', '[', ']', '{', '}', ',', ':', '.', ';', '@', '=', '->']);
    }

    tokenize(code, language) {
        switch (language.toLowerCase()) {
            case 'python':
                return this.tokenizePython(code);
            case 'javascript':
            case 'js':
                return this.tokenizeJavaScript(code);
            case 'html':
                return this.tokenizeHTML(code);
            case 'css':
                return this.tokenizeCSS(code);
            default:
                return this.tokenizePlainText(code);
        }
    }

    tokenizePython(code) {
        const tokens = [];
        let current = 0;
        const length = code.length;

        while (current < length) {
            let char = code[current];

            // Skip whitespace but preserve it as a token for indentation
            if (/\s/.test(char)) {
                const start = current;
                while (current < length && /\s/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('whitespace', code.slice(start, current), start, current));
                continue;
            }

            // Python-style comments (starting with #)
            if (char === '#') {
                const start = current;
                while (current < length && code[current] !== '\n') {
                    current++;
                }
                tokens.push(new Token('comment', code.slice(start, current), start, current));
                continue;
            }

            // Python triple quotes for docstrings
            if (char === '"' || char === "'") {
                const quote = char;
                const start = current;
                
                // Check for triple quotes
                if (code.slice(current, current + 3) === quote.repeat(3)) {
                    current += 3;
                    while (current < length && code.slice(current, current + 3) !== quote.repeat(3)) {
                        current++;
                    }
                    if (current < length) current += 3;
                    tokens.push(new Token('string', code.slice(start, current), start, current));
                    continue;
                }

                // Regular string handling
                current++;
                let isEscaped = false;
                while (current < length) {
                    if (code[current] === '\\' && !isEscaped) {
                        isEscaped = true;
                        current++;
                        continue;
                    }
                    if (code[current] === quote && !isEscaped) {
                        break;
                    }
                    isEscaped = false;
                    current++;
                }
                current++;
                tokens.push(new Token('string', code.slice(start, current), start, current));
                continue;
            }

            // Rest of the existing tokenization logic...
            return this._tokenizeGeneric(code, this.pythonKeywords);
        }
    }

    tokenizeJavaScript(code) {
        return this._tokenizeGeneric(code, this.jsKeywords);
    }

    tokenizeHTML(code) {
        const tokens = [];
        let current = 0;
        const length = code.length;

        while (current < length) {
            let char = code[current];

            // HTML Tags
            if (char === '<') {
                const start = current;
                let isClosingTag = code[current + 1] === '/';
                current++;

                while (current < length && char !== '>') {
                    char = code[current];
                    current++;
                }

                tokens.push(new Token('tag', code.slice(start, current), start, current));
                continue;
            }

            // HTML Attributes
            if (/[a-zA-Z-]/.test(char) && tokens.length > 0 && tokens[tokens.length - 1].type === 'tag') {
                const start = current;
                while (current < length && /[a-zA-Z0-9-]/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('attribute', code.slice(start, current), start, current));
                continue;
            }

            // String literals
            if (char === '"' || char === "'") {
                const start = current;
                const quote = char;
                current++;

                while (current < length && code[current] !== quote) {
                    current++;
                }
                current++;
                tokens.push(new Token('string', code.slice(start, current), start, current));
                continue;
            }

            // Whitespace
            if (/\s/.test(char)) {
                const start = current;
                while (current < length && /\s/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('whitespace', code.slice(start, current), start, current));
                continue;
            }

            // Other characters
            tokens.push(new Token('text', char, current, current + 1));
            current++;
        }

        return tokens;
    }

    tokenizeCSS(code) {
        const tokens = [];
        let current = 0;
        const length = code.length;

        while (current < length) {
            let char = code[current];

            // Selectors
            if (char === '.' || char === '#' || /[a-zA-Z*]/.test(char)) {
                const start = current;
                while (current < length && !/[{\s]/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('selector', code.slice(start, current), start, current));
                continue;
            }

            // Properties
            if (/[a-zA-Z-]/.test(char) && tokens.length > 0 && tokens[tokens.length - 1].value.includes('{')) {
                const start = current;
                while (current < length && /[a-zA-Z-]/.test(code[current])) {
                    current++;
                }
                const property = code.slice(start, current);
                const type = this.cssProperties.has(property) ? 'property' : 'unknown';
                tokens.push(new Token(type, property, start, current));
                continue;
            }

            // Values
            if (char === ':') {
                tokens.push(new Token('operator', char, current, current + 1));
                current++;
                const start = current;
                while (current < length && code[current] !== ';') {
                    current++;
                }
                tokens.push(new Token('value', code.slice(start, current).trim(), start, current));
                continue;
            }

            // Comments
            if (char === '/' && code[current + 1] === '*') {
                const start = current;
                current += 2;
                while (current < length && !(code[current - 1] === '*' && code[current] === '/')) {
                    current++;
                }
                current++;
                tokens.push(new Token('comment', code.slice(start, current), start, current));
                continue;
            }

            // Whitespace and other characters
            if (/\s/.test(char)) {
                const start = current;
                while (current < length && /\s/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('whitespace', code.slice(start, current), start, current));
            } else {
                tokens.push(new Token('delimiter', char, current, current + 1));
                current++;
            }
        }

        return tokens;
    }

    _tokenizeGeneric(code, keywords) {
        const tokens = [];
        let current = 0;
        const length = code.length;

        while (current < length) {
            let char = code[current];

            // Whitespace
            if (/\s/.test(char)) {
                const start = current;
                while (current < length && /\s/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('whitespace', code.slice(start, current), start, current));
                continue;
            }

            // Comments
            if (char === '/' && code[current + 1] === '/') {
                const start = current;
                while (current < length && code[current] !== '\n') {
                    current++;
                }
                tokens.push(new Token('comment', code.slice(start, current), start, current));
                continue;
            }

            // Multi-line comments
            if (char === '/' && code[current + 1] === '*') {
                const start = current;
                current += 2;
                while (current < length && !(code[current - 1] === '*' && code[current] === '/')) {
                    current++;
                }
                current++;
                tokens.push(new Token('comment', code.slice(start, current), start, current));
                continue;
            }

            // String literals
            if (char === '"' || char === "'") {
                const start = current;
                const quote = char;
                let isEscaped = false;
                current++;

                while (current < length) {
                    if (code[current] === '\\' && !isEscaped) {
                        isEscaped = true;
                        current++;
                        continue;
                    }
                    if (code[current] === quote && !isEscaped) {
                        break;
                    }
                    isEscaped = false;
                    current++;
                }
                current++;
                tokens.push(new Token('string', code.slice(start, current), start, current));
                continue;
            }

            // Numbers
            if (/[0-9]/.test(char)) {
                const start = current;
                while (current < length && /[0-9.]/.test(code[current])) {
                    current++;
                }
                tokens.push(new Token('number', code.slice(start, current), start, current));
                continue;
            }

            // Identifiers and keywords
            if (/[a-zA-Z_$]/.test(char)) {
                const start = current;
                while (current < length && /[a-zA-Z0-9_$]/.test(code[current])) {
                    current++;
                }
                const value = code.slice(start, current);
                const type = keywords.has(value) ? 'keyword' : 'identifier';
                tokens.push(new Token(type, value, start, current));
                continue;
            }

            // Operators and delimiters
            let isOperator = false;
            for (let i = 3; i >= 1; i--) {
                const op = code.slice(current, current + i);
                if (this.operators.has(op)) {
                    tokens.push(new Token('operator', op, current, current + i));
                    current += i;
                    isOperator = true;
                    break;
                }
            }
            if (isOperator) continue;

            if (this.delimiters.has(char)) {
                tokens.push(new Token('delimiter', char, current, current + 1));
                current++;
                continue;
            }

            // Unknown characters
            tokens.push(new Token('unknown', char, current, current + 1));
            current++;
        }

        return tokens;
    }
}

// Export for use in code-editor component
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SyntaxTokenizer, Token };
} else {
    window.SyntaxTokenizer = SyntaxTokenizer;
    window.Token = Token;
} 