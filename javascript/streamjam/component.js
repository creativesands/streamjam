import {writable} from "svelte/store";


export class Component {
    constructor(id, parentId, server, type, kwargs, client) {
        this.id = id
        this.parentId = parentId
        this.type = type
        this.client = client
        this.stores = {}
        this.rpcs = {}
        this.messageHandlerTopics = []

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
            this.messageHandlerTopics.push(topic)
            console.debug('Setting new value for', storeName, value)
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
        this.messageHandlerTopics.forEach(this.client.removeMessageHandler)
        this.client.wsSend('destroy-component', [this.id])
    }
}