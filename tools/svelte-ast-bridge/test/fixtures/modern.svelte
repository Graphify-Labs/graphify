<script>
  let visible = true;
  let items = [{ id: 1, title: 'one' }];
  let promise = Promise.resolve(items[0]);
  let element;
  let Component;
  let action;
  let transition;
  let flip;
  let attachment;
  const html = '<strong>html</strong>';
</script>

<!-- Comment -->
<svelte:head><title>Corpus</title></svelte:head>
<svelte:window on:click={() => visible = !visible} />
<svelte:document on:selectionchange={() => visible} />
<svelte:body class:active={visible} />
<svelte:element this="section">dynamic element</svelte:element>
<svelte:boundary><p>boundary</p></svelte:boundary>
<slot name="legacy" />
<Component
  title={items[0].title}
  {...items[0]}
  let:item
  on:ready={() => visible}
  class:active={visible}
  style:color={visible ? 'red' : 'blue'}
  use:action={items}
  transition:transition={items}
  {@attach attachment}
/>
<input bind:this={element} />

{#if visible}
  {@html html}
{:else}
  {@debug visible}
{/if}

{#each items as item (item.id)}
  <div animate:flip>{item.title}</div>
{:else}
  <p>empty</p>
{/each}

{#await promise}
  <p>pending</p>
{:then value}
  {@const title = value.title}
  <p>{title}</p>
{:catch error}
  <p>{error.message}</p>
{/await}

{#key visible}<p>keyed</p>{/key}
{#snippet row(value)}<span>{value.title}</span>{/snippet}
{@render row(items[0])}
{let declaration = items[0]}
