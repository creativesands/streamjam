<script>
    import { getContext, onDestroy, onMount } from "svelte"
    import VirtualList from 'svelte-virtual-list';

    const client = getContext('streamjam')
    window.dev_client = client

    const MAX_LOGS = 1000; // Maximum number of logs to keep
    const RETENTION_HOURS = 1; // Keep logs from last hour by default

    let isOpen = $state(false)
    let isPaused = $state(false)
    let activeTab = $state('Network')
    let tabs = $state.raw(['Components', 'Network', 'Memory', 'Server'])
    let networkLogs = $state(client.devToolLogs)
    let virtualList = $state(null)
    let filterText = $state('')
    let listKey = $state(0)
    let showScrollToBottom = $state(false)
    let containerRef = $state(null);
    let messageFilter = $state('all'); // 'all', 'sent', 'recv'

    // Global keyboard shortcut for widget toggle
    const handleGlobalKeydown = (e) => {
        if (e.code === 'Period' && e.metaKey && e.altKey) {
            e.preventDefault();
            isOpen = !isOpen;
        }
    };

    onMount(() => {
        window.addEventListener('keydown', handleGlobalKeydown);
    });

    onDestroy(() => {
        window.removeEventListener('keydown', handleGlobalKeydown);
    });

    // Keyboard shortcuts
    $effect(() => {
        if (!isOpen) return;
        
        const handleKeydown = (e) => {
            if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                document.querySelector('.toolbar input[type="text"]')?.focus();
            } else if (e.key === 'c' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                clearLogs();
            } else if (e.key === 'p' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                isPaused = !isPaused;
            }
        };

        window.addEventListener('keydown', handleKeydown);
        return () => window.removeEventListener('keydown', handleKeydown);
    });

    let filteredLogs = $derived(
        filterText || messageFilter !== 'all'
            ? networkLogs.filter(log => {
                const matchesFilter = !filterText || 
                    JSON.stringify(log.content).toLowerCase().includes(filterText.toLowerCase());
                const matchesType = messageFilter === 'all' || 
                    (messageFilter === 'sent' && log.type === 'message-out') ||
                    (messageFilter === 'recv' && log.type === 'message-in');
                return matchesFilter && matchesType;
            })
            : networkLogs
    );

    // Keep track of which logs are open
    let openStates = $state(new Map());

    function clearLogs() {
        client.devToolLogs = [];
        networkLogs = [];
        openStates.clear();
        listKey++;
    }

    function pruneOldLogs() {
        const cutoff = Date.now() - (RETENTION_HOURS * 60 * 60 * 1000);
        networkLogs = networkLogs.filter(log => log.time > cutoff);
        
        // Also prune if too many logs
        if (networkLogs.length > MAX_LOGS) {
            networkLogs = networkLogs.slice(-MAX_LOGS);
        }
    }

    function scrollToBottom() {
        if (containerRef) {
            containerRef.scrollTop = containerRef.scrollHeight;
        }
    }

    function handleScroll(e) {
        const target = e.target;
        const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 50;
        showScrollToBottom = !atBottom && networkLogs.length > 0;
    }

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

    $effect(() => {
        if (!isPaused) {
            const interval = setInterval(() => {
                // Preserve open states when updating logs
                const newLogs = client.devToolLogs.map(log => ({
                    ...log,
                    _open: openStates.get(log.time) || false
                }));
                networkLogs = newLogs;
                // pruneOldLogs();
                
                // Auto scroll to bottom after update
                if (!showScrollToBottom) {
                    scrollToBottom();
                }
            }, 100);

            return () => clearInterval(interval);
        }
    });

    function toggleLogOpen(log) {
        const newState = !!!log._open;
        log._open = newState;
        if (newState) {
            openStates.set(log.time, true);
        } else {
            openStates.delete(log.time);
        }
    }
</script>

<div class="container" 
    class:open={isOpen} 
    onclick={() => {isOpen = true}}
    onkeydown={(e) => {if (e.key === 'Enter') isOpen = true}}
    role="button"
    tabindex="0">
    <div class="header">
        <div class="logo"></div>
        {#if isOpen}
            <div class="tab-headers">
                {#each tabs as tab}
                    <div class="tab-name" 
                        data-tab-name="{tab}" 
                        class:active={activeTab === tab}
                        onclick={() => activeTab = tab}
                        role="tab"
                        tabindex="0"
                        onkeydown={(e) => {if (e.key === 'Enter') activeTab = tab}}
                    >{tab}</div>
                {/each}
            </div>
            <div class="toolbar">
                <div class="type-filters">
                    <label class="type-filter">
                        <input 
                            type="radio" 
                            name="message-type"
                            value="all"
                            checked={messageFilter === 'all'}
                            onclick={(e) => {
                                e.stopPropagation();
                                messageFilter = 'all';
                            }}
                        >
                        <span><span class="recv">↓</span><span class="send">↑</span> All</span>
                    </label>
                    <label class="type-filter">
                        <input 
                            type="radio" 
                            name="message-type"
                            value="sent"
                            checked={messageFilter === 'sent'}
                            onclick={(e) => {
                                e.stopPropagation();
                                messageFilter = 'sent';
                            }}
                        >
                        <span><span class="send">↑</span> Sent</span>
                    </label>
                    <label class="type-filter">
                        <input 
                            type="radio" 
                            name="message-type"
                            value="recv"
                            checked={messageFilter === 'recv'}
                            onclick={(e) => {
                                e.stopPropagation();
                                messageFilter = 'recv';
                            }}
                        >
                        <span><span class="recv">↓</span> Recv</span>
                    </label>
                </div>
                <input 
                    type="text" 
                    placeholder="Filter messages (⌘K)"
                    bind:value={filterText}
                    onclick={(e) => e.stopPropagation()}
                >
                <button class="icon-button" onclick={(e) => {
                    e.stopPropagation();
                    clearLogs();
                }} title="Clear logs (⌘C)">
                    🗑️
                </button>
                <button class="icon-button" class:paused={isPaused} onclick={(e) => {
                    e.stopPropagation();
                    isPaused = !isPaused;
                }} title={isPaused ? "Resume (⌘P)" : "Pause (⌘P)"}>
                    {#if isPaused}
                        ▶
                    {:else}
                        ⏸
                    {/if}
                </button>
                <button class="icon-button" onclick={(e) => {
                    e.stopPropagation();
                    isOpen = !isOpen;
                }} title="Close (⌘⌥.)">
                    ✕
                </button>
            </div>
        {/if}
    </div>
    {#if isOpen}
        <div class="tab-container">
            {#if activeTab === 'Network'}
                <div class="tab-content">
                    <div class="table-container">
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
                        </table>
                        <div class="virtual-list-container" 
                            bind:this={containerRef}
                            onscroll={handleScroll}>
                            <VirtualList 
                                bind:this={virtualList}
                                items={filteredLogs} 
                                key={listKey}
                                overscan={10}
                                let:item={log}>
                                <div class="virtual-row">
                                    <div class="col time" title={log.time}>{formatEpochTime(log.time)}</div>
                                    <div class="col network-type">
                                        {#if log.type === 'message-in'}
                                            <span class="recv">↓</span>
                                        {:else if log.type === 'message-out'}
                                            <span class="send">↑</span>
                                        {/if}
                                    </div>
                                    <div class="col component">Root</div>
                                    <div class="col message">
                                        <button 
                                            class:open={log?._open === true}
                                            onclick={() => toggleLogOpen(log)}
                                            onkeydown={(e) => {if (e.key === 'Enter') toggleLogOpen(log)}}
                                            tabindex="0">
                                            <pre>{JSON.stringify(log.content, null, 2)}</pre>
                                        </button>
                                    </div>
                                </div>
                            </VirtualList>
                            {#if showScrollToBottom}
                                <button 
                                    class="scroll-to-bottom"
                                    onclick={scrollToBottom}
                                    title="Scroll to bottom">
                                    ↓
                                </button>
                            {/if}
                        </div>
                    </div>
                </div>
            {:else}
                <div class="tab-content empty flex justify-center items-center">Coming Soon...</div>
            {/if}
        </div>
    {/if}
</div>

<style>
    .container {
        display: flex;
        position: fixed;
        bottom: 20px;
        left: calc(100% - 60px);
        width: 40px;
        height: 40px;
        border-radius: 40px;
        cursor: pointer;
        transition: all .3s ease;
        background-color: #060606;
        border: 1px solid #252525;
        box-shadow: none;
        justify-content: center;
        flex-direction: column;
        overflow: auto;
        color: rgb(153, 153, 153);
        z-index: 1000;
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
        display: flex;
        flex-direction: column;
        overflow: hidden;
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
        background-image: url("/streamjam.svg");
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
        align-items: center;
    }

    .toolbar input {
        background: #121212;
        color: inherit;
        outline: none;
        border: 1px solid #202020;
        border-radius: 5px;
        height: 24px;
        padding: 0 8px;
        min-width: 150px;
        font-size: 12px;
    }

    .toolbar button {
        background: #333333;
        border: 1px solid #202020;
        border-radius: 5px;
        color: inherit;
        cursor: pointer;
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

    col.time { width: 150px; }
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

    .message-content button {
        width: 100%;
        background: none;
        border: none;
        color: inherit;
        font: inherit;
        padding: 0;
        text-align: left;
        cursor: pointer;
    }

    .message-content button:hover {
        color: white;
    }

    .message-content button.open pre {
        white-space: pre-wrap;
        overflow: auto;
    }

    pre {
        font-family: monospace;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin: 0;
        max-width: 100%;
    }

    span.send {
        color: #44F696;
    }

    span.recv {
        color: #7527E9;
    }

    .virtual-list-container {
        height: 300px;
        overflow-y: auto !important;
        overflow-x: hidden;
    }

    .virtual-row {
        display: flex;
        border-bottom: 1px solid #202020;
        font-size: 12px;
        min-height: 25px;
        height: auto;
    }

    .virtual-row .col {
        padding: 2px 3px;
        border-right: 1px solid #202020;
        overflow: hidden;
        min-height: 25px;
        height: auto;
        display: flex;
        align-items: center;
    }

    .virtual-row .col.time { 
        width: 150px;
        flex-shrink: 0;
    }
    
    .virtual-row .col.network-type { 
        width: 50px;
        flex-shrink: 0;
        justify-content: center;
        font-weight: bolder;
    }
    
    .virtual-row .col.component { 
        width: 200px;
        flex-shrink: 0;
    }
    
    .virtual-row .col.message {
        flex-grow: 1;
        height: auto;
        overflow: visible;
    }

    .virtual-row .col.message button {
        width: 100%;
        height: auto;
        min-height: 25px;
        background: none;
        border: none;
        color: inherit;
        font: inherit;
        padding: 0;
        text-align: left;
        cursor: pointer;
        overflow: visible;
        display: flex;
        align-items: center;
    }

    .virtual-row .col.message button:hover {
        color: white;
    }

    .virtual-row .col.message pre {
        font-family: monospace;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin: 0;
        max-width: 100%;
        font-size: 11px;
        height: auto;
        flex: 1;
    }

    .virtual-row .col.message button.open pre {
        white-space: pre-wrap;
        overflow: visible;
        height: auto;
    }

    /* Remove these as they're now redundant */
    .message-content,
    .message-content button,
    .message-content button:hover,
    .message-content button.open pre {
        display: none;
    }

    .virtual-row:hover {
        background-color: rgba(255, 255, 255, 0.05);
    }

    .table-container {
        display: flex;
        flex-direction: column;
    }

    .network-table {
        flex-shrink: 0;
    }

    .virtual-list-container {
        flex-grow: 1;
        overflow: hidden;
    }

    .icon-button {
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        padding: 0;
        background: #060606;
        opacity: 0.5;
        transition: opacity 0.2s;
    }

    .icon-button:hover {
        opacity: 0.8;
    }

    .icon-button.selected {
        opacity: 1;
    }

    .icon-button.selected:hover {
        opacity: 0.8;
    }

    /* Pause button styles */
    button.icon-button.paused {
        background: #444;
        opacity: 1;
    }

    button.icon-button.paused:hover {
        opacity: 0.8;
    }

    .tab-container {
        flex-grow: 1;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    .tab-content {
        flex-grow: 1;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    .type-filters {
        display: flex;
        gap: 1em;
        align-items: center;
        border: 1px solid #232323;
        padding: 0 .5em;
        border-radius: 4px;
        height: 24px;
    }

    .type-filter {
        display: flex;
        align-items: center;
        gap: 2px;
        cursor: pointer;
    }

    .type-filter input[type="radio"] {
        margin: 0;
        cursor: pointer;
        min-width: auto;
    }

    .type-filter span {
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 2px;
    }

    .scroll-to-bottom {
        position: absolute;
        bottom: 20px;
        right: 20px;
        width: 32px;
        height: 32px;
        border-radius: 16px;
        background: #333;
        border: 1px solid #202020;
        color: inherit;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 16px;
        opacity: 0.8;
        transition: opacity 0.2s;
    }

    .scroll-to-bottom:hover {
        opacity: 1;
        background: #444;
    }

    .tab-name {
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 4px;
    }

    .tab-name:hover {
        background: rgba(255, 255, 255, 0.1);
    }

    .virtual-list-container {
        position: relative;
    }
</style>
