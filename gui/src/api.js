export const API_BASE_URL = new URL(process.env.REACT_APP_API_URL || window.location.origin)

export function apiUrl(path) {
    return new URL(path, API_BASE_URL).toString()
}

export function rpcUrl() {
    const url = new URL('/rpc', API_BASE_URL)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return url.toString()
}

export function callRpc(method, params = [], timeout = 30000) {
    const client = window.rpcClient
    if (!client?.ready) {
        return Promise.reject(new Error('Disconnected from the server. Wait for reconnection before retrying.'))
    }
    return client.call(method, params, timeout)
}

export function subscribeConnection(handler) {
    window.addEventListener('rpc-connection', handler)
    return () => window.removeEventListener('rpc-connection', handler)
}
