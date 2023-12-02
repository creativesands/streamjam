<script>
    import { setContext } from "svelte"
    import { StreamJamClient } from "./index"
    import Root from "./components/Root.svelte"

    const client = new StreamJamClient('ws://localhost:7755/client-1')
    let client_connection = client.connect()

    setContext('streamjam', client)
    setContext('__parentId', 'root')
</script>

{#await client_connection}
    Connecting...
{:then _}
    <Root />
{/await}
