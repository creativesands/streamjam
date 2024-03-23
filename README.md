# StreamJam

StreamJam is a structured and slightly opinionated framework that brings websocket-based 
Remote Procedure Call (RPC) architecture to web development. It enables you to create full-stack 
stateful components that seamlessly bridge the gap between the frontend and backend, allowing you 
to develop modern, highly interactive web applications with a tighter coupling and 
perceived state synchronization.

## Features

- **Full-stack Components**: Build components that combine server-side logic with client-side UI, providing a unified development experience.
- **Real-time Updates**: Create real-time, collaborative applications with seamless communication and state updates across multiple clients.
- **Websocket-based RPC and Streaming**: Leverage the power of RPC over WebSockets to facilitate direct method invocation, bringing your web development experience closer to real programming. May REST, rest in peace.
- **Automatic State Synchronization**: Enjoy automatic state synchronization between the server and client, eliminating the need for explicit data-binding or state management code.

---
```python
from streamjam import Component

class Counter(Component):                       #  StreamJam Component definition.
    count: int = 0                              #  Component state declaration.

    class Client:                               #  Client side Svelte code embedded within Python.
        """@                                    #  @ marks this docstring as Svelte code.
        <div>Count: {count}</div>               // Component state is available to use here directly.
        <button on:click={inc}>Add 1</button>   // Call methods defined as RPC for event handling and more.
        """

    @Component.rpc
    async def inc(self):
        self.count += 1                         # Assignments to component state are auto-synced with the client.
```
---

## Setup for Developers

### Setting up library
- Clone Streamjam from Github
- `pip install -e .`
- cd to `javascript/streamjam`
- `npm i`
- `npm link`

### StreamJam VSCode Plugin
StreamJam comes with a VSCode plugin that provides syntax highlighting and intellisense for
Svelte code that is embedded within a streamjam component's python file.

- [Install StreamJam Tools](https://marketplace.visualstudio.com/items?itemName=Creativesands.streamjam-tools)


### Creating new project
- Run the following command to create a new StreamJam project:  
`streamjam create`
  - project_name: Simple StreamJam
  - project_slug: simple_streamjam
  - project_slug: Simple project to get started with StreamJam

Once the project is created, create a new terminal for each of the following commands:
- **StreamJam Compiler**:  
  This command will watch for changes in your project and build the corresponding frontend files.
  - `cd simple_streamjam`
  - `streamjam build`
- **StreamJam Frontend Setup**: 
  - `cd .build`
  - `npm i`
  - `npm link streamjam`
  - `npm run dev`
- **StreamJam Server**:
  - `cd ../..` Parent of simple_streamjam directory
  - `python -m simple_streamjam.main`
  - The server does not yet auto-reload on changes. Use ctrl-c to terminate and restart.

Open the project in VSCode. You're now ready to build some awesome stuff.

---

## StreamJam — A Crash Course

### Project Structure

The following is the file structure created by `streamjam create` when creating a new project.

```text
project_home/
├── main.py
├── components/
│   └── root.py
├── public/
│   └── streamjam.svg
├── package.json
├── requirements.txt
│--------------------------
├── .build/
│   ├── index.html
│   ├── project.json
│   ├── src/
│   │   ├── App.svelte
│   │   ├── main.js
│   │   └── components/
│   │       └── Root.svelte
│   └── public/
│       └── streamjam.svg
```

The contents of `.build` are created by `streamjam build` command. Notice that python files in 
the components directory gets compiled to `.svelte` files if they contain a streamjam component 
class definition. 


### Creating a new StreamJam component

StreamJam components must be placed within the `components` directory. `root.py` defines the `Root` 
component of the application. Let's create a basic hello-world Root component.

```python
# root.py
from streamjam import Component

class Root(Component):
    name: str = 'World'

    class Client:
        """@
        <p>What is your name: <input type="text" bind:value={name} /></p>
        <h2>Hello {name}</h2>
        
        <style>
        h2 { color: #8BC34A; }
        </style>
        """
```

On save of root.py, `streamjam build` will compile this to `Root.svelte` file in the build directory.
Follow the url displayed by `npm run dev` to view the app in your browser. As you type text into the
input field, you should see it immediately being reflected in the greeting below.

> Note: please restart the python server to run the updated code.

The following are the main concepts of StreamJam:
- Component
  - Client
  - RPC Method
  - Event Dispatch
  - Event Handler
  - State Update Handler
  - Service Event Handler
- Service
- StreamJam DevTools
