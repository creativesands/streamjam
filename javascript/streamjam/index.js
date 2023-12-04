import { writable } from "svelte/store"

export const ID = () => '_' + Math.random().toString(36).substring(2, 9);

class Component {
    constructor(id, parentId, server, type, kwargs, client) {
        this.id = id
        this.parentId = parentId
        this.type = type
        this.client = client
        this.stores = {}
        this.rpcs = {}

        if (server === true) {
            this.client.wsSend('add-component', [this.id, this.parentId, this.type, kwargs])
        }
    }

    newStore(storeName, initialValue=null) {
        const this_ = this
        const { subscribe, set, update } = writable(initialValue)

        const topic = ['store-value', this.id, storeName].join('>')
        this.client.registerMessageHandler(topic, (value) => {
            set(value)
            console.log('setting new value for', storeName, value)
        })

        const store = {
            subscribe,
            set(value) {
                update(_ => value)
                this_.client.wsSend('store-set', [this_.id, storeName, value])
            }
        }
        this.stores[storeName] = store
        return store
    }

    proxyRPC(rpcName) {
        const this_ = this

        const rpc = async function () {
            const reqId = this_.client.wsSend('exec-rpc', [this_.id, rpcName, Array.from(arguments)])
            let [_, content] = await this_.client.collectResponse(reqId)
            return content
        }

        this.rpcs[rpcName] = rpc
        return rpc
    }

    destroy() {
        // remove message handlers?
    }
}

export class StreamJamClient {
    constructor(addr) {
        this.addr = addr
        this.ws = null
        this.isConnected = false
        this.promises = {}
        this.messageHandlerRegistry = {}
        this.components = {}

        this._resolveState = null
        this._restoreState = new Promise((resolve) => {this._resolveState = resolve})
        this.state = null
        this.isRestored = false
    }

    async connect() {
        let resolveConnection
        let hasConnected = new Promise((resolve) => {resolveConnection = resolve})

        this.ws = new WebSocket(this.addr)

        this.ws.addEventListener('open', e => {
            console.info('Connected to StreamJam Server at:', this.addr)
            this.isConnected = true
            resolveConnection()
        })

        this.ws.addEventListener('close', e => {
            console.info('Disconnect from StreamJam Server at:', this.addr)
            this.isConnected = false
        })

        this.ws.addEventListener('message', this.messageHandler(this))

        this.registerMessageHandler('app-state', this._resolveState)

        await hasConnected
        this.state = await this._restoreState
        this.isRestored = !!this.state
    }

    messageHandler(this_) {
        return function _messageHandler(e) {
            console.log('received:', e.data)
            const [reqId, topic, content] = JSON.parse(e.data)
            console.info('Message from server:', reqId, topic, this_.messageHandlerRegistry)

            if (topic in this_.messageHandlerRegistry) {
                console.log('calling', topic, content)
                this_.messageHandlerRegistry[topic](content)
            } else {
                console.log(topic, 'not found')
            }

            if (reqId in this_.promises) {
                let resolveResponse = this_.promises[reqId]
                resolveResponse([topic, content])
                delete this_.promises[reqId]
            }
        }
    }

    registerMessageHandler(topic, handler) {
        this.messageHandlerRegistry[topic] = handler
    }

    wsSend(topic, content=null) {
        const reqId = ID()
        this.ws.send(JSON.stringify([reqId, topic, content]))
        return reqId
    }

    async collectResponse(reqId) {
        return new Promise(resolveResponse => {
            this.promises[reqId] = resolveResponse
        })
    }

    newComponent(id, parentId, server, type, kwargs) {
        const component = new Component(id, parentId, server, type, kwargs, this)
        this.components[id] = component
        return component
    }

    destroyComponent(component) {
        component.destroy()
        delete this.components[component.id]
    }
}
