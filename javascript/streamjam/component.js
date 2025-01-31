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
        const self = this
        const { subscribe, set, update } = writable(initialValue)

        const topic = ['store-value', this.id, storeName].join('>')
        this.client.registerMessageHandler(topic, (value) => {
            set(value)
            // console.debug('Setting new value for', storeName, value)
        })
        this.messageHandlerTopics.push(topic)

        const store = {
            subscribe,
            set(value) {
                update(_ => value)
                self.client.wsSend('store-set', [self.id, storeName, value])
            }
        }
        this.stores[storeName] = store
        return store
    }

    proxyRPC(rpcName) {
        const self = this

        const rpc = async function () {
            const reqId = self.client.wsSend('exec-rpc', [self.id, rpcName, Array.from(arguments)])
            let [_, content] = await self.client.collectResponse(reqId)
            return content
        }

        this.rpcs[rpcName] = rpc
        return rpc
    }

    destroy() {
        this.messageHandlerTopics.forEach(this.client.removeMessageHandler.bind(this.client))
        this.client.wsSend('destroy-component', [this.id])
    }
}