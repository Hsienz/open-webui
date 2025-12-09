<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { socket } from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	interface ModelContainer {
		model: string;
		status: string;
	}
	let modelContainers: ModelContainer[] = [];
	let loading = true;

	const containerHandler = async (event, cb) => {
		console.log(JSON.stringify(event));
		const type = event?.data?.type ?? null;
		const data = event?.data?.data ?? null;
		if (type === 'container:model') {
		}
	};
	onMount(async () => {
		loading = true;
		$socket?.on('container', containerHandler);

		const token = localStorage.token;
		const modelList = await fetch(`${WEBUI_API_BASE_URL}/containers/models`, {
			method: 'GET',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		})
			.then(async (res) => {
				if (!res.ok) throw await res.json();
				return res.json();
			})
			.catch((err) => {
				console.error(err);
				return null;
			});

		console.log('model list: ', modelList);
		if (!modelList) {
			loading = false;
			return;
		}

		for (const model of modelList) {
			const containerInfo = await fetch(`${WEBUI_API_BASE_URL}/containers/model/${model}`)
				.then(async (res) => {
					if (!res.ok) throw await res.json();
					return res.json();
				})
				.catch((err) => {
					console.error(err);
					return null;
				});

			if (containerInfo) {
				modelContainers.push({
					model,
					status: containerInfo.status
				});
			}
		}
		loading = false;
	});

	onDestroy(async () => {
		$socket?.off('container');
	});
</script>

<div>
	{#each modelContainers as container (container.model)}
		{container.model}
	{/each}
</div>
