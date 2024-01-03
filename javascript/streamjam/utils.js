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