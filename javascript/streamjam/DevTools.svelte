<script>
    import { getContext } from "svelte"

    const client = getContext('streamjam')

    window.dev_client = client

    let isOpen = false
    let activeTab = 'Network'
    let tabs = ['Components', 'Network', 'Memory', 'Server']
    let networkLogs = client.devToolLogs

    function formatEpochTime(epochTime, showDate=false) {
        const date = new Date(epochTime);

        const year = date.getFullYear();
        const month = (date.getMonth() + 1).toString().padStart(2, '0'); // Months are zero-indexed
        const day = date.getDate().toString().padStart(2, '0');

        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        const seconds = date.getSeconds().toString().padStart(2, '0');
        const milliseconds = date.getMilliseconds().toString().padStart(3, '0');

        if (showDate) {
            return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}.${milliseconds}`;
        } else {
            return `${hours}:${minutes}:${seconds}.${milliseconds}`;
        }
    }

    function toggleMessageExpand(e) {
        e.currentTarget.classList
    }

    setInterval(() => {
        networkLogs = client.devToolLogs
    }, 100)
</script>


<div class="container" class:open={isOpen} on:click={() => {isOpen = true}}>
    <div class="header">
        <div class="logo"></div>
        {#if isOpen}
            <div class="tab-headers">
                {#each tabs as tab}
                    <div class="tab-name"  data-tab-name="{tab}" class:active={activeTab === tab}>{tab}</div>
                {/each}
            </div>
            <div class="toolbar">
                <input type="text" placeholder="Filter Components">
                <button on:click|stopPropagation={() => {isOpen = !isOpen}}>x</button>
            </div>
        {/if}
    </div>
    {#if isOpen}
        <div class="tab-container">
            {#if activeTab === 'Network'}
                <div class="tab-content">
                    <table class="network-table">
                        <colgroup>
                            <col class="time">
                            <col class="network-type">
                            <col class="component">
                            <col class="message">
                        </colgroup>
                        <thead>
                        <tr>
                            <th>Time</th>
                            <th class="network-type"><span class="recv">↓</span> / <span class="send">↑</span></th>
                            <th>Component</th>
                            <th>Message</th>
                        </tr>
                        </thead>
                        <tbody>
                        {#each networkLogs as log}
                            <tr>
                                <td>{formatEpochTime(log.time)}</td>
                                <td class="network-type">
                                    {#if log.type === 'message-in'}
                                        <span class="recv">↓</span>
                                    {:else if log.type === 'message-out'}
                                        <span class="send">↑</span>
                                    {/if}
                                </td>
                                <td>Root</td>
                                <td class="message-content">
                                    <pre class:open={log?._open === true} on:click={() => {log._open = !!!log._open}}>{JSON.stringify(log.content, null, 2)}</pre>
                                </td>
                            </tr>
                        {/each}
                        </tbody>
                    </table>
                </div>
            {:else}
                <div class="tab-content empty">Coming Soon...</div>
            {/if}
        </div>
    {/if}
</div>


<style>
    .container {
        display: flex;
        position: absolute;
        bottom: 20px;
        left: calc(100% - 60px);
        width: 40px;
        height: 40px;
        border-radius: 40px;
        cursor: pointer;
        transition: all .3s ease;
        background-color: #000000;
        box-shadow: none;
        justify-content: center;
        flex-direction: column;
        overflow: auto;
        color: rgb(153, 153, 153);
    }

    .container:hover {
        box-shadow: 0 0 25px 0 #7527E9;
    }

    .container.open:hover {
    }

    .container.open {
        width: calc(100% - 20px);
        height: 350px;
        left: 10px;
        bottom: 10px;
        box-shadow: none;
        justify-content: left;
        border-radius: 8px;
        box-sizing: border-box;
        cursor: auto;
    }

    .header {
        display: flex;
        justify-content: center;
        align-items: center;
        position: sticky;
        top: 0;
        background-color: #000000;
    }

    .open .header {
        justify-content: space-between;
        padding: 10px;
    }

    .logo {
        height: 20px;
        width: 20px;
        background-position: center;
        background-image: url("/streamjam-logo.svg");
        background-size: contain;
        background-repeat: no-repeat;
        cursor: pointer;
    }

    .open .logo {
        margin: 0 15px;
    }

    .toolbar {
        display: flex;
        gap: 10px;
    }

    .toolbar input {
        background: #333333;
        color: inherit;
        outline: none;
        border: 1px solid #202020;
        border-radius: 5px;
        padding: 2px 4px;
    }

    .toolbar button {
        background: #333333;
        border: 1px solid #202020;
        border-radius: 5px;
        font-size: 12px;
        padding: 3px 8px;
    }

    .tab-headers {
        display: flex;
        gap: 30px;
    }

    .tab-name {
        font-size: 14px;
    }

    .tab-name.active {
        color: white;
    }

    table {
        font-size: 12px;
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        position: relative;
    }

    th, td {
        border: 1px solid #202020;
        text-align: left;
        padding: 2px 3px;
    }

    thead th {
        background-color: #000000;
        position: sticky;
        top: 0; /* Adjust this value as needed */
        z-index: 1; /* Ensure the header is above other content */
        padding: 6px 3px;
    }

    /* Optional: Add some styling for the sticky header */
    thead th::after {
        content: '';
        display: block;
        position: absolute;
        left: 0;
        bottom: 0;
        width: 100%;
        border-bottom: 1px solid #202020;
    }

    col.time { width: 100px; }
    col.network-type { width: 50px; }
    col.component { width: 200px; }
    col.message {}

    th.network-type,
    td.network-type {
        font-weight: bolder;
        text-align: center;
    }

    .message-content {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
    }

    .message-content:hover {
        color: white;
    }

    pre {
        font-family: monospace;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin: 0; /* Remove default margin */
        max-width: 100%; /* Ensure it doesn't overflow the td */
    }

    pre.open {
        white-space: pre-wrap; /* Wrap text */
        overflow: auto; /* Add scrollbars if needed */
    }

    span.send {
        color: #44F696;
    }

    span.recv {
        color: #7527E9;
    }
</style>
