import React from 'react'
import ReactDOM from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'katex/dist/katex.min.css'
import './style.css'
import Messenger from './Messenger'
import {Client as RpcClient} from 'rpc-websockets'
import {rpcUrl} from './api'

function connectToServer() {
    const rpcClient = new RpcClient(rpcUrl(), {reconnect: true, reconnect_interval: 1000, max_reconnects: 0})
    const root = ReactDOM.createRoot(document.getElementById('root'))
    window.rpcClient = rpcClient
    root.render(
        <React.StrictMode>
            <Messenger />
        </React.StrictMode>
    )
    document.querySelector('.main-loader')?.remove()

    rpcClient.on('open', () => {
        window.dispatchEvent(new Event('rpc-connection'))
    })

    rpcClient.on('close', (event) => {
        console.info('Socket closed. Reconnecting…', event)
        window.dispatchEvent(new Event('rpc-connection'))
    })

    rpcClient.on('error', (event) => {
        console.error('WebSocket error:', event)
    })

    rpcClient.on('show_alert', (message) => {
        alert(Array.isArray(message) ? message[0] : message)
    })

    // A reload or transient disconnection must not shut down the backend.
    window.addEventListener('pagehide', () => rpcClient.close())
    window.addEventListener('pageshow', (event) => {
        if (event.persisted) rpcClient.connect()
    })
}

window.addEventListener('load', (event) => {
    connectToServer()

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('./serviceWorker.js')
    }
})
