export function isImage(fileName) {
    return /\.(jpg|jpeg|png|gif|webp|avif)$/i.test(fileName)
}

export function getUiTimestamp() {
    return window.performance.now()
}
