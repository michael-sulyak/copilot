import React, {Fragment, useMemo} from 'react'

const STATUS_META = {
    in_progress: {
        label: 'In progress',
        className: 'in-progress',
        iconClassName: null,
    },
    done: {
        label: 'Done',
        className: 'done',
        iconClassName: 'fa-check',
    },
    failed: {
        label: 'Failed',
        className: 'failed',
        iconClassName: 'fa-triangle-exclamation',
    },
}

function getStatusMeta(status) {
    return (
        STATUS_META[status] ?? {
            label: status || 'Unknown',
            className: 'unknown',
            iconClassName: 'fa-circle',
        }
    )
}

function getToolCalls(payload) {
    return Array.isArray(payload?.tool_calls) ? payload.tool_calls : []
}

function getDisplayValue(value) {
    if (value === null || value === undefined || value === '') {
        return ''
    }

    let normalizedValue = value

    if (typeof value === 'string') {
        const trimmedValue = value.trim()

        if (!trimmedValue) {
            return ''
        }

        try {
            normalizedValue = JSON.parse(trimmedValue)
        } catch {
            return value
        }
    }

    if (typeof normalizedValue === 'string') {
        return normalizedValue
    }

    try {
        return JSON.stringify(normalizedValue, null, 2)
    } catch {
        return String(normalizedValue)
    }
}

function getOverallStatus(payloadStatus, toolCalls) {
    const hasInProgressCall = toolCalls.some((toolCall) => toolCall?.status === 'in_progress')
    const hasFailedCall = toolCalls.some((toolCall) => toolCall?.status === 'failed')

    if (payloadStatus === 'in_progress' || hasInProgressCall) {
        return 'in_progress'
    }

    if (hasFailedCall) {
        return 'failed'
    }

    if (payloadStatus === 'done') {
        return 'done'
    }

    return 'unknown'
}

function StatusIcon({status}) {
    const meta = getStatusMeta(status)

    if (status === 'in_progress') {
        return <span className="tool-call-step-spinner" aria-hidden="true" />
    }

    return <i className={`fa-solid ${meta.iconClassName}`} aria-hidden="true" />
}

function ToolCallSummary({status, toolCalls}) {
    const inProgressCall = [...toolCalls].reverse().find((toolCall) => toolCall?.status === 'in_progress')
    const failedCount = toolCalls.filter((toolCall) => toolCall?.status === 'failed').length
    const callCount = toolCalls.length

    if (status === 'in_progress') {
        return (
            <span>
                {callCount ? `${callCount} tool call${callCount === 1 ? '' : 's'}` : 'Waiting for tool call'}
                {inProgressCall?.tool_name ? ` · running ${inProgressCall.tool_name}` : ''}
            </span>
        )
    }

    if (status === 'failed') {
        return (
            <span>
                Finished with {failedCount} failed tool call{failedCount === 1 ? '' : 's'}
            </span>
        )
    }

    if (status === 'done') {
        return (
            <span>
                Completed {callCount} tool call{callCount === 1 ? '' : 's'}
            </span>
        )
    }

    return <span>Tool call status is unavailable</span>
}

function ToolCallPipeline({toolCalls, overallStatus}) {
    if (!toolCalls.length) {
        return (
            <div className="tool-call-pipeline-empty">
                <span className="tool-call-step-spinner" aria-hidden="true" />
                Preparing tools
            </div>
        )
    }

    return (
        <div className="tool-call-pipeline" aria-label="Tool call pipeline">
            {toolCalls.map((toolCall, index) => {
                const meta = getStatusMeta(toolCall?.status)
                const toolName = toolCall?.tool_name || `tool ${index + 1}`

                return (
                    <Fragment key={`${index}-${toolName}-${toolCall?.status || 'unknown'}`}>
                        {index > 0 && (
                            <span
                                className={`tool-call-arrow ${overallStatus === 'in_progress' ? 'in-progress' : ''}`}
                                aria-hidden="true"
                            >
                                →
                            </span>
                        )}
                        <span className={`tool-call-step ${meta.className}`} title={toolName}>
                            <StatusIcon status={toolCall?.status} />
                            <span className="tool-call-step-name">{toolName}</span>
                        </span>
                    </Fragment>
                )
            })}
        </div>
    )
}

function ToolCallPayloadBlock({title, value, tone = 'default'}) {
    const displayValue = getDisplayValue(value)

    if (!displayValue) {
        return null
    }

    return (
        <div className={`tool-call-payload-block ${tone}`}>
            <div className="tool-call-payload-title">{title}</div>
            <pre>{displayValue}</pre>
        </div>
    )
}

function ToolCallDetail({toolCall, index}) {
    const meta = getStatusMeta(toolCall?.status)
    const toolName = toolCall?.tool_name || `tool ${index + 1}`
    const hasResult = getDisplayValue(toolCall?.result)
    const hasError = getDisplayValue(toolCall?.error)

    return (
        <div className={`tool-call-detail ${meta.className}`}>
            <div className="tool-call-detail-header">
                <div className="tool-call-detail-title">
                    <StatusIcon status={toolCall?.status} />
                    <span>{toolName}</span>
                </div>
                <span className={`tool-call-status-badge ${meta.className}`}>{meta.label}</span>
            </div>

            <ToolCallPayloadBlock title="Arguments" value={toolCall?.arguments} />
            <ToolCallPayloadBlock title="Error" value={toolCall?.error} tone="error" />
            <ToolCallPayloadBlock title="Result" value={toolCall?.result} />

            {!hasResult && !hasError && toolCall?.status === 'in_progress' && (
                <div className="tool-call-waiting-result">Waiting for result…</div>
            )}
        </div>
    )
}

function ToolCall({message}) {
    const payload = message?.payload ?? {}
    const toolCalls = useMemo(() => getToolCalls(payload), [payload])
    const overallStatus = getOverallStatus(payload?.status, toolCalls)
    const meta = getStatusMeta(overallStatus)

    if (overallStatus === 'done' && toolCalls.length === 0) {
        return <Fragment/>
    }

    return (
        <div className="message d-flex tool-call-message">
            <div className={`tool-call-card ${meta.className}`}>
                <div className="tool-call-header">
                    <div className="tool-call-title">
                        <StatusIcon status={overallStatus} />
                        <span>
                            {overallStatus === 'in_progress' ? 'Tool processing' : 'Tool processing finished'}
                            {overallStatus === 'in_progress' && <span className="tool-call-animated-dots" aria-hidden="true" />}
                        </span>
                    </div>
                    <div className="tool-call-summary">
                        <ToolCallSummary status={overallStatus} toolCalls={toolCalls} />
                    </div>
                </div>

                <ToolCallPipeline toolCalls={toolCalls} overallStatus={overallStatus} />

                <details className="tool-call-details">
                    <summary>Details</summary>
                    <div className="tool-call-details-body">
                        {toolCalls.length ? (
                            toolCalls.map((toolCall, index) => (
                                <ToolCallDetail key={`${index}-${toolCall?.tool_name || 'tool'}`} toolCall={toolCall} index={index} />
                            ))
                        ) : (
                            <div className="tool-call-empty-details">No tool call details yet.</div>
                        )}
                    </div>
                </details>
            </div>
        </div>
    )
}

export default React.memo(ToolCall)
