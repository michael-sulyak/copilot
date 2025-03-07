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

function Markdown({content}) {
    return (
        <ReactMarkdown
            remarkPlugins={[
                [remarkMath, {singleDollarTextMath: true}],
                [remarkGfm, {singleTilde: false}],
            ]}
            rehypePlugins={[rehypeInlineCodeProperty, rehypeKatex]}
            components={{
                code(props) {
                    const {children, className, node, inline, ...rest} = props
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
                a({href, children, ...props}) {
                    return (
                        <a href={href} target="_blank" rel="noreferrer">
                            {children}
                        </a>
                    )
                },
            }}
            children={content}
        />
    )
}

export default React.memo(Markdown)
