export function isImage(fileName) {
    return fileName.match(/.(jpg|jpeg|png|gif)$/i)
}

export function getTimestampNs() {
    return window.performance.now() * 1e6
}
