export const ID = () => '_' + Math.random().toString(36).substring(2, 9);


export class AsyncQueue {
    constructor() {
        this.queue = []
        this.waitingResolvers = []
    }

    put(item) {
        if (this.waitingResolvers.length > 0) {
            const resolve = this.waitingResolvers.shift()
            resolve(item)
        } else {
            this.queue.push(item)
        }
    }

    async get() {
        if (this.queue.length > 0) {
            return Promise.resolve(this.queue.shift())
        } else {
            return new Promise((resolve) => {
                this.waitingResolvers.push(resolve)
            })
        }
    }
}


export function autoscroll(node) {
    let atBottom = true

    // Function to scroll to the bottom
    function scrollToBottom() {
        if (atBottom) {
            node.scrollTo({
                top: node.scrollHeight,
                behavior: 'smooth'
            })
        }
    }

    // Scroll to bottom initially
    scrollToBottom()

    // Handle scroll events
    function handleScroll() {
        // Check if the user has scrolled away from the bottom
        atBottom = node.scrollHeight - node.clientHeight <= node.scrollTop + 1
    }

    // Add scroll event listener
    node.addEventListener('scroll', handleScroll)

    // Observe changes in the content of the node
    const observer = new MutationObserver(scrollToBottom)
    observer.observe(node, { childList: true, subtree: true })

    return {
        destroy() {
            node.removeEventListener('scroll', handleScroll)
            observer.disconnect()
        }
    }
}