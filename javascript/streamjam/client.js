import { ID } from "./utils"
import { Component } from "./component"


export class StreamJamClient {
    constructor(addr) {
        this.addr = addr
        this.ws = null
        this.isConnected = false
        this.promises = {}
        this.messageHandlerRegistry = {}
        this.components = {}
        this.devToolLogs = []

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
            // console.debug('Received message:', e.data)
            const [reqId, topic, content] = JSON.parse(e.data)
            this_.devToolLogs.push({type: 'message-in', time: Date.now(), content: {reqId, topic, content}})
            // console.debug('Message from server:', reqId, topic, this_.messageHandlerRegistry)

            if (topic in this_.messageHandlerRegistry) {
                // console.debug('Calling handler for', topic, content)
                this_.messageHandlerRegistry[topic](content)
            } else {
                // console.debug('Topic not found:', topic)
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

    removeMessageHandler(topic) {
        delete this.messageHandlerRegistry[topic]
    }

    wsSend(topic, content=null) {
        const reqId = ID()
        this.devToolLogs.push({type: 'message-out', time: Date.now(), content: {reqId, topic, content}})
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