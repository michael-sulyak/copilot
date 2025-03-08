export function isImage(fileName) {
    return fileName.match(/.(jpg|jpeg|png|gif)$/i)
}

export function getTimestampNs() {
    return window.performance.now() * 1e6
}

export async function needToTurnOnVPN({addNotification}) {
    const location = await fetch('https://www.cloudflare.com/cdn-cgi/trace')
        .then((response) => response.text())
        .then((data) => data.match(/loc=(.*)/)[1])
        .catch((err) => addNotification(String(err)))

    return location === 'RU'
}
