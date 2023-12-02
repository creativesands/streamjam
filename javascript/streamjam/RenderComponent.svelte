<script>
    export let component_map
    export let component
</script>

<svelte:component
        this={component_map[component.type]}
        id="{component.id}"
        __restored="{true}"
        {...component.state}
/>

{#if component.children && component.children.length}
    {#each component.children as child}
        <svelte:self component_map component="{child}" />
    {/each}
{/if}