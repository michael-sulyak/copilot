import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import remarkGfm from 'remark-gfm'
import rehypeKatex from 'rehype-katex'

import {Prism as SyntaxHighlighter} from 'react-syntax-highlighter'
import {darcula as SyntaxHighlighterTheme} from 'react-syntax-highlighter/dist/esm/styles/prism'
import {visit} from 'unist-util-visit'
import mermaid from 'mermaid'


function CopyButton({getText, title = 'Copy', className = 'btn btn-sm btn-copy', style}) {
    const [icon, setIcon] = React.useState('copy')

    const handleClick = async () => {
        try {
            const text = typeof getText === 'function' ? getText() : String(getText ?? '')
            if (!text) {
                throw new Error('Nothing to copy')
            }

            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text)
            } else {
                // Fallback for older browsers
                const ta = document.createElement('textarea')
                ta.value = text
                document.body.appendChild(ta)
                ta.select()
                document.execCommand('copy')
                document.body.removeChild(ta)
            }

            setIcon('check')
            setTimeout(() => setIcon('copy'), 1500)
        } catch {
            setIcon('bug')
            setTimeout(() => setIcon('copy'), 1500)
        }
    }

    return (
        <button
            type="button"
            className={className}
            aria-label={title}
            title={title}
            onClick={handleClick}
            style={style}
        >
            <i className={`fa-solid fa-${icon}`}></i>
        </button>
    )
}

function MermaidBlock({code}) {
    const ref = React.useRef(null)

    React.useEffect(() => {
        let canceled = false
        const id = 'mmd-' + Math.random().toString(36).slice(2)

        async function render() {
            try {
                mermaid.initialize({
                    startOnLoad: false,
                    securityLevel: 'strict',
                    theme: 'dark',
                })

                const {svg} = await mermaid.render(id, code)

                if (!canceled && ref.current) {
                    ref.current.innerHTML = svg
                }
            } catch (e) {
                if (ref.current) {
                    ref.current.innerText = 'Mermaid render error: ' + (e?.message || e)
                }
            }
        }

        render()

        return () => {
            canceled = true

            if (ref.current) {
                ref.current.innerHTML = ''
            }
        }
    }, [code])

    return (
        <div className="mermaid-container" style={{position: 'relative'}}>
            <div ref={ref}/>
            <CopyButton
                getText={() => code}
                title="Copy Mermaid source"
            />
        </div>
    )
}

function rehypeInlineCodeProperty() {
    return function (tree) {
        visit(tree, 'element', function (node, index, parent) {
            if (node.tagName === 'code') {
                if (!node.properties) {
                    node.properties = {}
                }

                if (parent && parent.tagName === 'pre') {
                    node.properties.inline = false
                } else {
                    node.properties.inline = true
                }
            }
        })
    }
}

function Markdown({content}) {
    return (
        <div>
            <ReactMarkdown
                remarkPlugins={[
                    [remarkMath, {singleDollarTextMath: true}],
                    [remarkGfm, {singleTilde: false}],
                ]}
                rehypePlugins={[rehypeInlineCodeProperty, rehypeKatex]}
                components={{
                    code(props) {
                        const {children, className, inline, ...rest} = props
                        const match = /language-(\w+)/.exec(className || '')
                        const language = match ? match[1] : ''

                        if (inline) {
                            return (
                                <code {...rest} className={className}>
                                    {children}
                                </code>
                            )
                        }

                        if (language === 'mermaid') {
                            const raw = Array.isArray(children) ? children.join('') : (children ?? '')
                            const code = String(raw).replace(/\n$/, '').trim()
                            if (!code || code === 'undefined' || code === 'null') {
                                return null
                            }
                            return <MermaidBlock code={code}/>
                        }

                        const raw = Array.isArray(children) ? children.join('') : (children ?? '')
                        const codeStr = String(raw).replace(/\n$/, '')

                        return (
                            <div className="code-container" style={{position: 'relative'}}>
                                <SyntaxHighlighter
                                    {...rest}
                                    PreTag="div"
                                    children={codeStr}
                                    language={language}
                                    style={SyntaxHighlighterTheme}
                                />
                                <CopyButton
                                    getText={() => codeStr}
                                    title="Copy code"
                                />
                            </div>
                        )
                    },
                    a({href, children}) {
                        return (
                            <a href={href} target="_blank" rel="noreferrer">
                                {children}
                            </a>
                        )
                    },
                }}
                children={content}
            />
        </div>
    )
}

export default React.memo(Markdown)
