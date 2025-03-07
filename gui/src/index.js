import React from 'react'
import ReactDOM from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'katex/dist/katex.min.css'
import './style.css'
import Chat from './Chat'
import {Client as RpcClient} from 'rpc-websockets'


function connectToServer() {
    const rpcClient = new RpcClient('ws://localhost:8123/rpc')
    window.rpcClient = rpcClient

    rpcClient.on('open', (event) => {
        const root = ReactDOM.createRoot(document.getElementById('root'))

        root.render(
            <React.StrictMode>
                <Chat/>
            </React.StrictMode>,
        )

        document.querySelector('.main-loader')?.remove()
    })

    rpcClient.on('close', (event) => {
        console.log(`Socket is closed. Reconnect will be attempted in 1 second.\n${event.reason}`)
    })

    rpcClient.on('error', (event) => {
        alert(`Socket encountered error: ${event.message}\nClosing socket`)

        rpcClient.close()
    })

    rpcClient.on('show_alert', (message) => {
        alert(message)
    })

    window.addEventListener('beforeunload', async (event) => {
        await rpcClient.call('finish', [])
        await rpcClient.close()
    })
}

window.addEventListener('load', (event) => {
    connectToServer()

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('./serviceWorker.js')
    }
})
