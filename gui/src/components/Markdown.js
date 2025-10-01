import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import remarkGfm from 'remark-gfm'
import rehypeKatex from 'rehype-katex'

import {Prism as SyntaxHighlighter} from 'react-syntax-highlighter'
import {darcula as SyntaxHighlighterTheme} from 'react-syntax-highlighter/dist/esm/styles/prism'
import {visit} from 'unist-util-visit'


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

function addCopyBtnToCode(root = document) {
    const blocks = root.querySelectorAll('pre > div > code')

    for (const code of blocks) {
        const pre = code.parentElement.parentElement

        if (!pre) {
            continue
        }

        if (pre.querySelector('button.btn-copy')) {
            continue
        }

        if (!pre.style.position) {
            pre.style.position = 'relative'
        }

        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'btn btn-sm btn-copy'
        btn.setAttribute('aria-label', 'Copy code')
        btn.innerHTML = '<i class="fa-solid fa-copy"></i>'

        btn.addEventListener('click', async () => {
            const text = code.innerText
            try {
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
                btn.innerHTML = '<i class="fa-solid fa-check"></i>'
                setTimeout(() => (btn.innerHTML = '<i class="fa-solid fa-copy"></i>'), 1500)
            } catch {
                btn.innerHTML = '<i class="fa-solid fa-bug"></i>'
                setTimeout(() => (btn.innerHTML = '<i class="fa-solid fa-copy"></i>'), 1500)
            }
        })

        pre.appendChild(btn)
    }
}

function Markdown({content}) {
    const containerRef = React.useRef(null)

    React.useEffect(() => {
        if (containerRef.current) {
            addCopyBtnToCode(containerRef.current)
        }
    }, [content])

    return (
        <div ref={containerRef}>
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

                        return inline ? (
                            <code {...rest} className={className}>
                                {children}
                            </code>
                        ) : (
                            <SyntaxHighlighter
                                {...rest}
                                PreTag="div"
                                children={String(children).replace(/\n$/, '')}
                                language={language}
                                style={SyntaxHighlighterTheme}
                            />
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
